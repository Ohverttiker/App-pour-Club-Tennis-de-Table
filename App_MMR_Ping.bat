@echo off
cd /d "%~dp0"

echo Lancement de l'application Tennis de Table...
echo.

echo Installation / mise à jour des dependances...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

echo.
echo Ouverture dans le navigateur...
python -m streamlit run app.py

pause