sudo apt-get update
sudo apt-get install -y \
  python3.10 python3.10-venv python3-dev build-essential cmake \
  libatlas-base-dev libjasper-dev libhdf5-dev \
  libqtgui4 libqt4-test libharfbuzz0b libwebp6 \
  i2c-tools

# Enable I2C and SPI
sudo raspi-config        # Interface Options → I2C → Enable, SPI → Enable
sudo reboot


ls /dev/spidev*          # should see /dev/spidev0.0
i2cdetect -y 1           # optional, PN532 will show at 0x24 if I2C used


cd ~
git clone https://github.com/vivekreddy9036/TriSecure.git
cd TriSecure


pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

pip install adafruit-circuitpython-pn532 adafruit-blinka RPi.GPIO

export TRISECURE_MODE=development


python -m trisecure.main
# or
python trisecure/main.py