#!/bin/bash

# Import the configuration file
source milix.config

# Check if all variables are set
if [[ -z "$WIFI_SSID" || -z "$WIFI_PASSWORD" || -z "$WIFI_BAND" ]]; then
    echo "Error: One or more configuration variables are empty."
    exit 1
fi

# Get the OS version
OS_VERSION=$(lsb_release -rs)

# Check if the OS is Debian 12
if [[ "$OS_VERSION" != "12" ]]; then
    echo "Error: This script requires Debian 12. You are running Debian $OS_VERSION."
    exit 1
fi

echo "Milix Installation"
echo "Package install"
if [ -f "${ARKIME_DEB}" ]; then
    echo "File ${ARKIME_DEB} exists, skip download."
else
    echo "File ${ARKIME_DEB} does not exist, download now."
    wget ${ARKIME_DEB_URL}
fi
sudo apt update;
sudo apt install -y hostapd libpcap-dev bridge-utils ./${ARKIME_DEB}
echo "Copy arkime config"
sudo bash -c 'source ./milix.config && envsubst < ./arkime/config.ini > /opt/arkime/etc/config.ini'
sudo mkdir /opt/arkime/logs/
#https://arkime.com/faq
sudo bash -c 'echo "OPTIONS=\"--insecure\"" >> /opt/arkime/etc/capture.env'
sudo bash -c 'echo "OPTIONS=\"--insecure\"" >> /opt/arkime/etc/viewer.env'
echo "arkime installation done"
sudo systemctl disable arkimecapture.service
sudo systemctl disable arkimeviewer.service


# Ref: https://dnsmonster.dev/docs/getting-started/installation/
echo "DNSMonster installation"
sudo chown root:root ./dns_monster/dnsmonster
sudo chmod 755 ./dns_monster/dnsmonster
sudo cp ./dns_monster/dnsmonster /usr/sbin
echo "Copy dnsmonster config"
sudo bash -c 'source ./milix.config && envsubst < ./dns_monster/dnsmonster.ini > /etc/dnsmonster.ini'
echo "dnsmonster installation done"
echo "Create dnsmonster service"
sudo bash -c 'source ./milix.config && envsubst < ./dns_monster/dnsmonster.service > /etc/systemd/system/dnsmonster.service'
sudo chown root:root /etc/systemd/system/dnsmonster.service
sudo chmod 644 /etc/systemd/system/dnsmonster.service
sudo systemctl daemon-reload
echo "Create dnsmonster service done"

# Ref: https://blog.soracom.com/ja-jp/2022/10/31/how-to-build-wifi-ap-with-bridge-by-raspberry-pi/
# disable wpa_supplicant
sudo systemctl stop wpa_supplicant.service
sudo systemctl mask wpa_supplicant.service
# add pre start to kill wlan related service
sudo systemctl unmask hostapd.service
sudo systemctl disable hostapd.service
cat << _EOT_ | sudo SYSTEMD_EDITOR=tee systemctl edit hostapd.service
# Ref: /lib/systemd/system/raspberrypi-net-mods.service
[Unit]
Before = networking.service
[Service]
ExecStartPre = /bin/sh -c '/bin/rm -f /var/lib/systemd/rfkill/*.mmc*wlan'
ExecStartPre = /usr/sbin/rfkill unblock wifi
_EOT_
# add the hostapd config file
cat << _EOT_ | sudo tee /etc/hostapd/hostapd.conf
interface=${WIFI_INTERFACE}
bridge=br0
driver=nl80211
ssid=${WIFI_SSID}
hw_mode=g
channel=${WIFI_BAND}
macaddr_acl=0
ignore_broadcast_ssid=0
auth_algs=1
ieee80211n=1
wme_enabled=1
country_code=TW
wpa=2
wpa_passphrase=${WIFI_PASSWORD}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
wpa_group_rekey=86400
_EOT_
sudo chmod 600 /etc/hostapd/hostapd.conf
# add the bridge config file
cat << _EOT_ | sudo tee /etc/network/interfaces.d/br0.conf
auto br0
iface br0 inet dhcp
  bridge_ports ${LAN_INTERFACE} ${WIFI_INTERFACE}
_EOT_

# Add crontab
# add the cronjob bash script
cat << 'EOF' > ~/milix_service_restart.sh
#!/bin/bash

sudo systemctl restart hostapd.service
sudo systemctl --no-pager status hostapd.service
echo "!!hostapd restart done!!"
sleep 5

sudo systemctl restart networking.service
sudo systemctl --no-pager status networking.service
echo "!!network restart!!"
sleep 5

sudo systemctl restart dnsmonster
sudo systemctl --no-pager status dnsmonster

sudo systemctl restart arkimecapture.service
sudo systemctl --no-pager status arkimecapture.service

sudo systemctl restart arkimeviewer.service
sudo systemctl --no-pager status arkimeviewer.service

sudo systemctl --no-pager status hostapd.service
EOF
# add the crontab
( crontab -l; echo "30 5 * * * /bin/bash $HOME/milix_service_restart.sh" ) | crontab -
sudo chmod +x $HOME/milix_service_restart.sh
echo "Installed the cron job!"
