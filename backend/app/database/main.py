from fastapi import FastAPI
from app.database.database import engine, Base
from app.database import models

# إنشاء الجداول فوراً في قاعدة البيانات SQLite محلياً
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Local Smart Notebook API")

@app.get("/")
def read_root():
    return {"message": "Local Smart Notebook Backend is up and running successfully!"}