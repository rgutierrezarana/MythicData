import os
import sys
import logging
from typing import Optional, List
from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

# Importaciones locales
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.config import settings
from backend.database import get_db, init_db
from backend.schemas import CardSummary, CardDetail, FilterMetadata, PaginatedResponse
from backend import crud

# Logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("MTGExplorerAPI")

# Inicialización de FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API REST de alto rendimiento para exploración de cartas de Magic: The Gathering, análisis de precios multitienda y series temporales.",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Inicializa la base de datos y ejecuta auto-seeding si es necesario."""
    logger.info("Iniciando aplicación MTG Card Explorer...")
    try:
        init_db()
        logger.info("Base de datos inicializada correctamente.")
    except Exception as e:
        logger.error(f"Error durante el inicio de base de datos: {e}")


# ==============================================================================
# Endpoints REST API (/api/v1/)
# ==============================================================================

@app.get(f"{settings.API_V1_PREFIX}/health", tags=["Health"])
def health_check():
    """Verificación de salud del servicio y de la base de datos."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }


@app.get(
    f"{settings.API_V1_PREFIX}/cards",
    response_model=PaginatedResponse[CardSummary],
    tags=["Cards"]
)
def list_cards(
    q: Optional[str] = Query(None, description="Búsqueda por texto en nombre o tipo de carta"),
    oracle_text: Optional[str] = Query(None, description="Búsqueda en texto de reglas (Oracle text)"),
    colors: Optional[str] = Query(None, description="Colores separados por coma (ej. W,U,B,R,G,C)"),
    card_type: Optional[str] = Query(None, description="Tipo de carta (ej. Creature, Instant, Sorcery, Artifact, Land)"),
    rarity: Optional[str] = Query(None, description="Rareza (Common, Uncommon, Rare, Mythic)"),
    mana_value_min: Optional[float] = Query(None, description="Coste de maná convertido mínimo (CMC)"),
    mana_value_max: Optional[float] = Query(None, description="Coste de maná convertido máximo (CMC)"),
    set_code: Optional[str] = Query(None, description="Código de set (ej. MH3, FDN, BLB)"),
    has_price: Optional[bool] = Query(None, description="Filtrar solo cartas con cotización de precio"),
    price_min: Optional[float] = Query(None, description="Precio mínimo en USD/EUR"),
    price_max: Optional[float] = Query(None, description="Precio máximo en USD/EUR"),
    sort_by: str = Query("name", description="Campo de orden: name, mana_value, price, release_date, collector_number"),
    order: str = Query("asc", description="Dirección de orden: asc, desc"),
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(24, ge=1, le=100, description="Tamaño de página (máx. 100)"),
    db: Session = Depends(get_db)
):
    """
    Retorna un listado paginado de cartas con soporte para filtros combinados multivariables.
    """
    color_list = [c.strip().upper() for c in colors.split(",") if c.strip()] if colors else None

    return crud.get_cards_paginated(
        db=db,
        q=q,
        oracle_text=oracle_text,
        colors=color_list,
        card_type=card_type,
        rarity=rarity,
        mana_value_min=mana_value_min,
        mana_value_max=mana_value_max,
        set_code=set_code,
        has_price=has_price,
        price_min=price_min,
        price_max=price_max,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size
    )


@app.get(
    f"{settings.API_V1_PREFIX}/cards/{{uuid}}",
    response_model=CardDetail,
    tags=["Cards"]
)
def get_card_detail(uuid: str, db: Session = Depends(get_db)):
    """
    Retorna el detalle completo de una carta, incluyendo desglose de precios multitienda e historial.
    """
    card = crud.get_card_detail_by_uuid(db, uuid)
    if not card:
        raise HTTPException(status_code=404, detail=f"Carta con UUID '{uuid}' no encontrada.")
    return card


@app.get(
    f"{settings.API_V1_PREFIX}/cards/{{uuid}}/price-history",
    response_model=crud.CardPriceHistoryResponse,
    tags=["Pricing"]
)
def get_card_price_history(
    uuid: str,
    provider: Optional[str] = Query(None, description="Filtrar por tienda (ej. tcgplayer, cardmarket, cardkingdom)"),
    game_format: Optional[str] = Query(None, description="Filtrar por formato (paper, mtgo)"),
    price_type: Optional[str] = Query(None, description="Filtrar por tipo de precio (retail, buylist)"),
    finish: Optional[str] = Query(None, description="Filtrar por acabado (normal, foil, etched)"),
    currency: Optional[str] = Query(None, description="Filtrar por moneda (USD, EUR)"),
    days: Optional[int] = Query(None, description="Ventana de días hacia atrás (ej. 7, 30, 90)"),
    db: Session = Depends(get_db)
):
    """
    Retorna la serie temporal detallada y estadísticas de cambio de precios (variación absoluta y porcentual)
    para una carta según los filtros de tienda, acabado, formato y tiempo aplicados.
    """
    return crud.get_card_price_history_filtered(
        db=db,
        uuid=uuid,
        provider=provider,
        game_format=game_format,
        price_type=price_type,
        finish=finish,
        currency=currency,
        days=days
    )


@app.get(
    f"{settings.API_V1_PREFIX}/filters/metadata",
    response_model=FilterMetadata,
    tags=["Filters"]
)
def get_filters_metadata(db: Session = Depends(get_db)):
    """
    Retorna metadatos de sets, tipos, rarezas y rangos de precio para alimentar selectores en la UI.
    """
    return crud.get_filter_metadata(db)


# ==============================================================================
# Servir Frontend SolidJS (Archivos Estáticos y Fallback SPA)
# ==============================================================================

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

if os.path.exists(frontend_dist):
    # Montar directorio dist
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Si la ruta apunta a un archivo estático existente en dist
        potential_file = os.path.join(frontend_dist, full_path)
        if os.path.isfile(potential_file):
            return FileResponse(potential_file)
        
        # Fallback para rutas de cliente SPA (index.html)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        
        return JSONResponse({"message": "Frontend en desarrollo. Acceda a /docs para la API."}, status_code=200)
else:
    @app.get("/", include_in_schema=False)
    def root_dev():
        return {
            "message": "MTG Explorer API en ejecución.",
            "docs": "/docs",
            "api": settings.API_V1_PREFIX,
            "frontend_status": "Compilar frontend con 'npm run build' en /frontend para servir SPA"
        }
