sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-dev \
  build-essential cmake \
  libhdf5-dev \
  libssl-dev libffi-dev




  pip install --upgrade pip wheel setuptools
pip install -r requirements.txt




export TRISECURE_MODE=development
python -m trisecure.main