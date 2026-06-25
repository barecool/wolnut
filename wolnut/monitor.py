import json
import os
import subprocess
import time
import logging
import wakeonlan
from wolnut.config import WolNutConfig

logger = logging.getLogger("wolnut")


class WolNutMonitor:
    def __init__(self, config: WolNutConfig):
        self.config = config
        self.state = self._load_state()
        self._ups_previous_status = {}

    def _load_state(self) -> dict:
        """Loads historical wake and power restoration timestamps from disk."""
        if os.path.exists(self.config.status_file):
            try:
                with open(self.config.status_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to read state file: {e}")
        return {"client_last_wake": {}, "ups_power_restored_time": {}}

    def _save_state(self):
        """Persists tracking metrics so state survives container/service restarts."""
        try:
            os.makedirs(os.path.dirname(self.config.status_file), exist_ok=True)
            with open(self.config.status_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    def fetch_ups_status(self, ups_name: str) -> tuple[Optional[str], int]:
        """Queries the network NUT instance using upsc utility tags."""
        device = self.config.nut[ups_name]
        target = f"{ups_name}@{device.hostname}:{device.port}"
        
        try:
            result = subprocess.run(["upsc", target], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                logger.error(f"Error executing upsc for {target}: {result.stderr.strip()}")
                return None, 0
            
            status = "UNKNOWN"
            battery = 100
            for line in result.stdout.strip().split("\n"):
                if "ups.status:" in line:
                    status = line.split(":", 1)[1].strip()
                elif "battery.charge:" in line:
                    try:
                        battery = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
            return status, battery
        except Exception as e:
            logger.error(f"Exception while connecting to NUT target {target}: {e}")
            return None, 0

    def is_host_online(self, host: str) -> bool:
        """Pings client device to check if it's already running."""
        try:
            result = subprocess.run(["ping", "-c", "1", "-W", "1", host], capture_output=True)
            return result.returncode == 0
        except Exception:
            return False

    def check_and_wake(self):
        """Core execution sweep iterating through all device states."""
        now = time.time()
        ups_data = {}

        # 1. Poll statuses for all unique UPS units
        for ups_name in self.config.nut.keys():
            status, battery = self.fetch_ups_status(ups_name)
            ups_data[ups_name] = {"status": status, "battery": battery}

            # Capture transition to Online (OL)
            prev = self._ups_previous_status.get(ups_name)
            if status and "OL" in status:
                if prev and "OL" not in prev:
                    logger.info(f"Power recovery detected on UPS: {ups_name}")
                    self.state["ups_power_restored_time"][ups_name] = now
                    self._save_state()
            self._ups_previous_status[ups_name] = status

        # 2. Evaluate rulesets for each configured client target
        for client in self.config.clients:
            local_ups = ups_data.get(client.ups, {"status": None, "battery": 0})
            master_ups = ups_data.get(self.config.master_ups, {"status": None, "battery": 0}) if self.config.master_ups else None

            local_online = local_ups["status"] and "OL" in local_ups["status"]
            master_online = master_ups and master_ups["status"] and "OL" in master_ups["status"]

            # Trigger logic: client's individual UPS is online OR global Master UPS is online
            has_power = local_online or master_online
            active_battery = local_ups["battery"] if local_online else (master_ups["battery"] if master_online else 0)

            if has_power and active_battery >= self.config.wake_on.min_battery_percent:
                # Find the most recent power restoration timestamp among matching sources
                t_local = self.state["ups_power_restored_time"].get(client.ups, 0)
                t_master = self.state["ups_power_restored_time"].get(self.config.master_ups, 0) if self.config.master_ups else 0
                restored_at = max(t_local, t_master)

                # Has the guard delay passed since power restoration?
                if now - restored_at >= self.config.wake_on.restore_delay_sec:
                    # Is the target device asleep?
                    if not self.is_host_online(client.host):
                        last_wake = self.state["client_last_wake"].get(client.mac, 0)
                        
                        # Has the reattempt cooldown timer expired?
                        if now - last_wake >= self.config.wake_on.reattempt_delay:
                            logger.info(f"Sending Wake-on-LAN magic packet to {client.name} ({client.mac})")
                            wakeonlan.send_magic_packet(client.mac)
                            self.state["client_last_wake"][client.mac] = now
                            self._save_state()

    def start(self, interval_sec: int = 10):
        """Runs the daemon service loop continuously."""
        logger.info("Starting Multi-UPS WolNut monitor loop daemon...")
        while True:
            try:
                self.check_and_wake()
            except Exception as e:
                logger.error(f"Error in execution cycle: {e}", exc_info=True)
            time.sleep(interval_sec)
