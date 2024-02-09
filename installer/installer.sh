#!/usr/bin/with-contenv bash
echo "************ Install Packages ************"
apk add -U --update --no-cache \
	git \
	python3 \
	py3-pip

echo "************ install python packages ************"
pip install --upgrade --no-cache-dir -U --break-system-packages \
	yq


echo "************ Setup Script Directory ************"
if [ ! -d /config/scripts ]; then
	mkdir -p /config/scripts
fi

echo "************ Download / Update Repo ************"
if [ -d /config/scripts/Radarr_Kodi ]; then
    git -C /config/scripts/Radarr_Kodi pull
else
    git clone https://github.com/jsaddiction/Radarr_Kodi.git /config/scripts/Radarr_Kodi
fi

echo "************ Install Script Dependencies ************"
pip install --upgrade pip --no-cache-dir --break-system-packages
pip install -r /config/scripts/Radarr_Kodi/requirements.txt --no-cache-dir --break-system-packages

if [ ! -f /config/scripts/Radarr_Kodi/settings.yaml ]; then
	echo "********** Adding Default Config ****************"
	cp /config/scripts/Radarr_Kodi/src/config/default_config.yaml /config/scripts/Radarr_Kodi/settings.yaml
fi

echo "************ Set Permissions ************"
chmod 777 -R /config/scripts/Radarr_Kodi

echo "************ Configuring Sonarr *********"
if [ ! -d /custom-services.d ]; then
    mkdir -p /custom-services.d
fi

if [ -f /custom-services.d/config_radarr.sh ]; then
	rm -rf /custom-services.d/config_radarr
fi

echo "Download AutoConfig service..."
curl https://raw.githubusercontent.com/jsaddiction/Radarr_Kodi/main/installer/config_radarr.sh -o /custom-services.d/RadarrKodiAutoConfig
echo "Done"

exit