# routers/placeholders.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/config', response_class=HTMLResponse)
async def config_page(request: Request):
    return templates.TemplateResponse(request, 'placeholder.html', {
        'active_tab': 'config', 'page_title': 'Configurazione'
    })


@router.get('/metrics', response_class=HTMLResponse)
async def metrics_page(request: Request):
    return templates.TemplateResponse(request, 'placeholder.html', {
        'active_tab': 'metrics', 'page_title': 'Metriche'
    })
