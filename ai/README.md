## ai
cd ai
conda activate {각자 가상환경}
pip install -r requirements.txt
python -m pip install "uvicorn[standard]"   
uvicorn server:app --host 127.0.0.1 --port 8000
