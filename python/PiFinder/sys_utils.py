import glob
import sh
from sh import iwgetid, wpa_cli, unzip
import socket
from PiFinder import utils

BACKUP_PATH = "/home/pifinder/PiFinder_data/PiFinder_backup.zip"


class Network:
    """
    Provides wifi network info
    """

    def __init__(self):
        self.wifi_txt = f"{utils.pifinder_dir}/wifi_status.txt"
        with open(self.wifi_txt, "r") as wifi_f:
            self._wifi_mode = wifi_f.read()

        self.populate_wifi_networks()

    def populate_wifi_networks(self):
        """
        Parses wpa_supplicant.conf to get current config
        """
        self._wifi_networks = []

        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "r") as wpa_conf:
            network_id = 0
            in_network_block = False
            for l in wpa_conf:
                if l.startswith("network={"):
                    in_network_block = True
                    network_dict = {
                        "id": network_id,
                        "ssid": None,
                        "psk": None,
                        "key_mgmt": None,
                    }

                elif l.strip() == "}" and in_network_block:
                    in_network_block = False
                    self._wifi_networks.append(network_dict)
                    network_id += 1

                elif in_network_block:
                    key, value = l.strip().split("=")
                    network_dict[key] = value.strip('"')

    def get_wifi_networks(self):
        return self._wifi_networks

    def delete_wifi_network(self, network_id):
        """
        Immediately deletes a wifi network
        """
        self._wifi_networks.pop(network_id)

        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "r") as wpa_conf:
            wpa_contents = list(wpa_conf)

        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "w") as wpa_conf:
            in_networks = False
            for l in wpa_contents:
                if not in_networks:
                    if l.startswith("network={"):
                        in_networks = True
                    else:
                        wpa_conf.write(l)

            for network in self._wifi_networks:
                ssid = network["ssid"]
                key_mgmt = network["key_mgmt"]
                psk = network["psk"]

                wpa_conf.write("\nnetwork={\n")
                wpa_conf.write(f'\tssid="{ssid}"\n')
                if key_mgmt == "WPA-PSK":
                    wpa_conf.write(f'\tpsk="{psk}"\n')
                wpa_conf.write(f"\tkey_mgmt={key_mgmt}\n")

                wpa_conf.write("}\n")

        self.populate_wifi_networks()

    def add_wifi_network(self, ssid, key_mgmt, psk=None):
        """
        Add a wifi network
        """
        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "a") as wpa_conf:
            wpa_conf.write("\nnetwork={\n")
            wpa_conf.write(f'\tssid="{ssid}"\n')
            if key_mgmt == "WPA-PSK":
                wpa_conf.write(f'\tpsk="{psk}"\n')
            wpa_conf.write(f"\tkey_mgmt={key_mgmt}\n")

            wpa_conf.write("}\n")

        self.populate_wifi_networks()
        if self._wifi_mode == "Client":
            # Restart the supplicant
            wpa_cli("reconfigure")

    def get_ap_name(self):
        with open(f"/etc/hostapd/hostapd.conf", "r") as conf:
            for l in conf:
                if l.startswith("ssid="):
                    return l[5:-1]
        return "UNKN"

    def set_ap_name(self, ap_name):
        if ap_name == self.get_ap_name():
            return
        with open(f"/tmp/hostapd.conf", "w") as new_conf:
            with open(f"/etc/hostapd/hostapd.conf", "r") as conf:
                for l in conf:
                    if l.startswith("ssid="):
                        l = f"ssid={ap_name}\n"
                    new_conf.write(l)
        sh.sudo("cp", "/tmp/hostapd.conf", "/etc/hostapd/hostapd.conf")

    def get_host_name(self):
        return socket.gethostname()

    def get_connected_ssid(self):
        """
        Returns the SSID of the connected wifi network or
        None if not connected or in AP mode
        """
        # get output from iwgetid
        _t = iwgetid(_ok_code=(0, 255)).strip()
        return _t.split(":")[-1].strip('"')

    def set_host_name(self, hostname):
        if hostname == self.get_host_name():
            return
        result = sh.sudo("hostnamectl", "set-hostname", hostname)

    def wifi_mode(self):
        return self._wifi_mode

    def set_wifi_mode(self, mode):
        if mode == self._wifi_mode:
            return
        if mode == "AP":
            go_wifi_ap()

        if mode == "Client":
            go_wifi_cli()

    def local_ip(self):
        if self._wifi_mode == "AP":
            return "10.10.10.1"

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.255.255.255", 1))
            ip = s.getsockname()[0]
        except:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip


def remove_backup():
    """
    Removes backup file
    """
    sh.sudo("rm", BACKUP_PATH, _ok_code=(0, 1))


def backup_userdata():
    """
    Back up userdata to a single zip file for later
    restore.  Returns the path to the zip file.

    Backs up:
        config.json
        observations.db
        obslist/*
    """

    remove_backup()

    _zip = sh.Command("zip")
    _zip(
        BACKUP_PATH,
        "/home/pifinder/PiFinder_data/config.json",
        "/home/pifinder/PiFinder_data/observations.db",
        glob.glob("/home/pifinder/PiFinder_data/obslists/*"),
    )

    return zip_path


def restore_userdata(zip_path):
    """
    Compliment to backup_userdata
    restores userdata
    OVERWRITES existing data!
    """
    unzip("-d", "/", "-o", zip_path)


def shutdown():
    """
    shuts down the Pi
    """
    print("SYS: Initiating Shutdown")
    sh.sudo("shutdown", "now")
    return True


def update_software():
    """
    Uses systemctl to git pull and then restart
    service
    """
    print("SYS: Running update")
    sh.bash("/home/pifinder/PiFinder/pifinder_update.sh")
    return True


def restart_pifinder():
    """
    Uses systemctl to restart the PiFinder
    service
    """
    print("SYS: Restarting PiFinder")
    sh.sudo("systemctl", "restart", "pifinder")
    return True


def restart_system():
    """
    Restarts the system
    """
    print("SYS: Initiating System Restart")
    sh.sudo("shutdown", "-r", "now")


def go_wifi_ap():
    print("SYS: Switching to AP")
    sh.sudo("/home/pifinder/PiFinder/switch-ap.sh")
    return True


def go_wifi_cli():
    print("SYS: Switching to Client")
    sh.sudo("/home/pifinder/PiFinder/switch-cli.sh")
    return True
