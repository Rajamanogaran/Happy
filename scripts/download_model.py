"""Explicitly download the requested model (about 480 MB); never checked into git."""
from pathlib import Path
from urllib.request import urlretrieve

path=Path(__file__).resolve().parents[1]/'models/tinyllama-1.1b-chat-v1.0.Q2_K.gguf'
url='https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q2_K.gguf'
if path.exists():
    print(f'Already exists: {path}')
else:
    path.parent.mkdir(exist_ok=True)
    temp=path.with_suffix('.part')
    print('Downloading TinyLlama Q2_K. See the model repository for license and model card.')
    try:
        urlretrieve(url,temp)
        with temp.open('rb') as f:
            if f.read(4)!=b'GGUF': raise ValueError('Download is not a GGUF model')
        temp.rename(path)
        print(f'Saved {path}')
    finally:
        temp.unlink(missing_ok=True)
