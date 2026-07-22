from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import admin, auth, matches, ml, reports
app=FastAPI(title=settings.app_name,version="0.1.0",description="Plataforma de inteligência estatística e value bets. Probabilidades são estimativas, não garantias.")
app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(auth.router,prefix="/api/v1"); app.include_router(matches.router,prefix="/api/v1"); app.include_router(reports.router,prefix="/api/v1"); app.include_router(ml.router,prefix="/api/v1"); app.include_router(admin.router,prefix="/api/v1")
@app.get("/health",tags=["Operação"])
async def health(): return {"status":"ok","service":settings.app_name}
