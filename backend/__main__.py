import os
import uvicorn

# Import loads the local .env before selecting the port.
from .main import app

if __name__ == '__main__':
    uvicorn.run(app,host='127.0.0.1',port=int(os.getenv('MONITOR_PORT','8787')))
