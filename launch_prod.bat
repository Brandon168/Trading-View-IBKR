@echo off
call .venv\Scripts\activate
uvicorn --host 0.0.0.0 --port 7000 main:app