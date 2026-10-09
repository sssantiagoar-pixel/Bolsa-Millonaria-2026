# Simulador Bolsa Millonaria: instalación y uso

## 1. Configurar el entorno en Anaconda (una sola vez)

1. Abre **Anaconda Prompt** (menú Inicio → "Anaconda Prompt").
2. Ve a la carpeta del proyecto:
   ```bash
   cd "C:\Users\sssan\OneDrive\Documentos\UNIVERSIDAD\PIC (PILOTO INVESTMENT CLUB)\COMPETICIONES\BOLSA MILLONARIA"
   ```
3. Crea el entorno desde `environment.yml`:
   ```bash
   conda env create -f environment.yml
   ```
   *Alternativa manual:*
   ```bash
   conda create -n bolsa_millonaria python=3.11 -y
   conda activate bolsa_millonaria
   pip install -r requirements.txt
   ```
4. Activa el entorno:
   ```bash
   conda activate bolsa_millonaria
   ```

## 2. Ejecutar la aplicación (cada día)

```bash
conda activate bolsa_millonaria
cd "C:\Users\sssan\OneDrive\Documentos\UNIVERSIDAD\PIC (PILOTO INVESTMENT CLUB)\COMPETICIONES\BOLSA MILLONARIA"
streamlit run app.py
```

Se abre el navegador en `http://localhost:8501`. Para detenerla: `Ctrl + C` en la terminal.

**¿No ves nada?**
- También puedes usar `python app.py` o el botón ▶ de Spyder/VS Code: la app detecta que no está corriendo dentro de Streamlit y se relanza sola con `streamlit run`.
- Si el puerto 8501 ya está ocupado por otra app (otra instancia de Streamlit), usa otro puerto y abre esa URL:
  ```bash
  streamlit run app.py --server.port 8502
  ```
- No uses `--server.headless true`: con esa opción el navegador no se abre solo.
- La primera carga tarda entre 20 y 40 s porque descarga ~2 años de precios. Mientras tanto verás "Running…" arriba a la derecha.

**Actualizar librerías** (si yfinance deja de descargar datos, suele arreglarse así):
```bash
pip install -U yfinance streamlit
```

## 3. Persistencia

- El portafolio vive en `st.session_state` y además se **autoguarda** en `portafolio_simulador.json` (misma carpeta). Si cierras el navegador o reinicias el PC, lo recuperas al volver a abrir la app.
- Barra lateral: **Exportar/Importar JSON** (copias de seguridad) y **Reiniciar a $100.000.000**.
- El día 1 del ensayo es la fecha del primer arranque (o del último reinicio).

## 4. Flujo diario sugerido (30 días)

1. **Antes de la apertura (BVC 9:30 a.m.)**: pestaña *Macro* (Brent, USD/COP, S&P) y *Estrategias & Riesgo*, para revisar el ranking y las rupturas.
2. **Plan**: escribe la tesis en *Bitácora*.
3. **Ejecución**: *Dashboard*, con el ticket de orden. Si el precio de Yahoo está atrasado, activa "precio manual" y usa el precio que ves en Trii.
4. **Semanal**: corre *Backtesting 30D* y recalcula el *Portafolio Óptimo* (MC y BL).
5. **Cierre**: descarga la entrada `.md` de la Bitácora y pégala en `PLANTILLA_BITACORA.md`.

## 5. Notas sobre datos

- Yahoo Finance usa el sufijo `.CL` para la BVC. Verificado el 8-oct-2026: los MGC (`TSLACO.CL`, `NVDACO.CL`, `AAPLCO.CL`, `MSFTCO.CL`, `AMZNCO.CL`, `GOOGLCO.CL`, `METACO.CL`) sí descargan. Si alguno falla, la app construye un **PROXY = precio en EE.UU. × USD/COP** y lo marca con ⚠️ en "Estado de descarga de datos".
- Bancolombia ahora cotiza como **Grupo Cibest**: `CIBEST.CL` y `PFCIBEST.CL`. Los tickers `PFBCOLOM.CL` y `BCOLOMBIA.CL` ya no tienen datos.
- Yahoo no publica `^COLCAP`, así que el benchmark es el ETF `ICOLCAP.CL`.
- El universo BVC tiene 37 activos en 6 sectores. En la barra lateral puedes filtrar por sector o marcar "Incluir TODAS" para escanear todo el mercado.
- **Liquidez:** las acciones con monto promedio diario menor al mínimo (por defecto $20.000.000) o con 8 o más de las últimas 20 ruedas sin negociar se marcan ⚪ ILÍQUIDA. Esas no entran en la selección automática del portafolio, pero puedes elegirlas en modo Manual.
- `TEVAICOL.CL` (ETF BTG Pactual TEVA) se listó en septiembre de 2026. Hasta que tenga unas 25 ruedas no aparece en señales, y necesita 60 para entrar al optimizador.
- La tasa libre de riesgo por defecto es 9% E.A. Ajústala al dato vigente de TES o IBR.
