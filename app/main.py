from fastapi import FastAPI
from app.database.database import engine, Base
from app.database import models
from app.api import auth, notebooks  # استيراد ملف الراوتر الجديد

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Local Smart Notebook API")

# تسجيل الراوتر عشان يظهر في الـ API
app.include_router(auth.router)
app.include_router(notebooks.router)

@app.get("/")
def read_root():
    return {"message": "Local Smart Notebook Backend is running successfully!"}