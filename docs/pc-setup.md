# Guía de la PC Windows (pruebas con Assetto Corsa)

Esta guía prepara la PC de juego para grabar telemetría real de Assetto Corsa
(AC original). Solo hace falta hacerla una vez; después basta con el paso 5.

> Estado: el adaptador de AC **todavía no se ha verificado con el juego**. El
> objetivo de esta guía es justamente hacer esa primera prueba.

Todos los comandos se escriben en **PowerShell** (menú Inicio → escribe
"PowerShell" → Enter). Copia una línea, pégala con clic derecho y pulsa Enter.

## 1. Instalar las herramientas

Usamos `winget`, el instalador que ya trae Windows 10 (1809 o posterior) y
Windows 11. Instala tres programas:

- **Git**: descarga y sube el código.
- **uv**: instala Python 3.12 y las dependencias del proyecto.
- **GitHub CLI (`gh`)**: inicia sesión en GitHub para poder clonar el repositorio privado.

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id GitHub.cli -e
```

Después **cierra PowerShell y ábrelo de nuevo** para que encuentre los
programas. Comprueba que están instalados:

```powershell
git --version
uv --version
gh --version
```

Si alguno dice "no se reconoce como comando", reinicia la PC y vuelve a probar.

No hace falta instalar Python a mano: `uv` descarga la versión correcta. Si ya
tienes otro Python instalado, no pasa nada; no interfiere.

## 2. Iniciar sesión en GitHub

```powershell
gh auth login
```

Responde: `GitHub.com` → `HTTPS` → `Yes` (usar las credenciales de GitHub para
git) → `Login with a web browser`. Copia el código que aparece, pulsa Enter, y
autoriza en el navegador con la cuenta **rguz0703**.

## 3. Descargar el proyecto

```powershell
cd $HOME\Documents
gh repo clone rguz0703/RaceEngineerAI
cd RaceEngineerAI
```

Mientras la Fase 2 no esté mergeada en `main`, cámbiate a su rama:

```powershell
git switch f2-ac-shared-memory
```

## 4. Preparar el entorno

```powershell
cd agent
uv sync
uv run raceengineer --version
uv run pytest
```

`uv sync` tarda un poco la primera vez. Los tests deben terminar en verde.

Para traer cambios nuevos en el futuro: `git pull` (en la carpeta del proyecto) y
luego `uv sync` dentro de `agent`.

## 5. Probar con Assetto Corsa

La memoria compartida de AC solo existe **mientras estás en pista** (en el menú
principal no). Pon AC en modo ventana o ventana sin bordes para poder cambiar a
PowerShell con Alt+Tab sin problemas.

### 5a. Volcado crudo (para fixtures)

1. Abre AC, elige coche y circuito, y sal a pista (práctica).
2. Con Alt+Tab vuelve a PowerShell (en la carpeta `agent`) y ejecuta:

   ```powershell
   uv run raceengineer dump-raw --seconds 30
   ```

3. Vuelve al juego y conduce durante esos 30 segundos. Si puedes, pasa por boxes
   y pausa el juego unos segundos (Esc); así el volcado incluye esos estados.
4. Al terminar verás algo como
   `Volcado guardado en data\dumps\ac-20261016-201500.acraw.gz: ...`.

### 5b. Grabar vueltas

1. Con el coche en pista, ejecuta:

   ```powershell
   uv run raceengineer record --source ac
   ```

2. Conduce **al menos 3 vueltas completas**. Apunta los tiempos que muestra el
   juego (o míralos después en la pantalla de resultados).
3. Vuelve a PowerShell y pulsa **Ctrl+C**. Se guarda todo y verás
   `Sesión N grabada: ... muestras`.
4. Compara los tiempos:

   ```powershell
   uv run raceengineer sessions
   uv run raceengineer laps N
   ```

   (cambia `N` por el número de la sesión). Cada vuelta completa debería quedar a
   menos de unas centésimas del tiempo del juego. La primera vuelta (salida de
   boxes) y la última (cortada con Ctrl+C) normalmente están incompletas.

### Si algo falla

- `No se encontró la memoria compartida de Assetto Corsa`: AC no está en pista.
  Sal a pista y repite.
- La grabación termina sola: AC volvió al menú (estado OFF). Es lo esperado.
- Durante una repetición (replay) o en pausa no se graban muestras.

## 6. Enviar los resultados al Mac

Copia y pega en el chat la salida de `sessions` y de `laps`, junto con los tiempos
que viste en el juego.

Para el volcado crudo, mira su tamaño en el mensaje final. Si pesa menos de 2 MB,
súbelo a la rama para usarlo como fixture de tests:

```powershell
New-Item -ItemType Directory -Force tests\fixtures
copy data\dumps\ac-AAAAMMDD-HHMMSS.acraw.gz tests\fixtures\ac_practice.acraw.gz
git add tests\fixtures\ac_practice.acraw.gz
git commit -m "Add real AC shared memory dump fixture"
git push
```

(cambia el nombre del archivo por el tuyo). La primera vez que hagas un commit en
la PC, git te pedirá tu nombre y correo:

```powershell
git config --global user.name "Raul Guzman"
git config --global user.email "tu-correo@ejemplo.com"
```

Si pesa más, graba otro con menos
segundos (`--seconds 10`).
