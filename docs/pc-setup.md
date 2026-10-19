# Guía de la PC Windows (pruebas con Assetto Corsa)

Esta guía prepara la PC de juego para grabar telemetría real de Assetto Corsa
(AC original). Solo hace falta hacerla una vez; después basta con el paso 5.

> Estado: el adaptador de AC **todavía no se ha verificado con el juego**. El
> objetivo de esta guía es justamente hacer esa primera prueba.

Todos los comandos se escriben en **PowerShell** (menú Inicio → escribe
"PowerShell" → Enter). Copia una línea, pégala con clic derecho y pulsa Enter.

## 0. Antes de empezar (PC de pruebas: Dell Precision 5810)

- El disco tiene dos sistemas: **arranca en la partición de Windows**, donde está
  instalado AC. Todo se hace ahí; el grabador debe correr en el mismo Windows
  que el juego.
- La GPU (Quadro K620, 2 GB) va justa para AC. Para la primera prueba pon
  gráficos **bajos** y modo **ventana sin bordes**: así puedes cambiar a
  PowerShell con Alt+Tab sin que el juego se cuelgue. La CPU (Xeon de 10
  núcleos) y la RAM (32 GB) sobran para grabar.

## 1. Instalar las herramientas

Necesitas tres programas:

- **Git**: descarga y sube el código. Ya está instalado en esta PC.
- **uv**: instala Python 3.12 y las dependencias del proyecto.
- **GitHub CLI (`gh`)**: inicia sesión en GitHub para poder clonar el repositorio privado.

Primero comprueba qué tienes:

```powershell
git --version
uv --version
gh --version
```

Instala solo los que digan "no se reconoce como comando":

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id GitHub.cli -e
```

Si tienes **GitHub Desktop** pero `git --version` falla, instala también Git con
la primera línea: GitHub Desktop trae su propio git, pero PowerShell no lo ve.

Después **cierra PowerShell y ábrelo de nuevo** y repite las tres comprobaciones.
Si alguna sigue fallando, reinicia Windows y vuelve a probar. Si `winget`
tampoco se reconoce, instala "App Installer" desde Microsoft Store.

**Python:** ya lo tienes instalado, y no estorba. El proyecto no lo usa: `uv`
descarga su propio Python 3.12 y lo guarda aparte, así que da igual qué versión
tengas.

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

## 5. Uso diario: grabar desde el dashboard

Desde la versión con "centro de control" ya no hace falta escribir comandos para
grabar. En la carpeta `agent`:

```powershell
uv run raceengineer serve --lan
```

Deja esa ventana abierta y abre el dashboard en el celular o en la Mac
(`http://<IP-de-la-PC>:8000`, la dirección que muestra la consola):

1. Arriba verás el estado del juego: **cerrado**, **en el menú** o **en pista**.
2. Pulsa **● Grabar**. Si todavía no estás en pista, el programa espera y
   arranca solo cuando salgas.
3. Mientras manejas, abre la pestaña **En vivo**: delta contra tu mejor vuelta
   en ese circuito y coche (verde vas ganando, rojo perdiendo), velocidad,
   marcha, RPM, acelerador, freno, volante y tu posición en el mapa. Si haces
   una vuelta limpia más rápida, pasa a ser la referencia.
4. Pulsa **■ Detener**, o simplemente vuelve al menú de AC: la sesión se guarda
   y aparece en la lista, lista para comparar.

Si cierras la ventana de `serve` (Ctrl+C) mientras grabas, lo grabado se guarda
igual.

Para probar el dashboard sin el juego (por ejemplo en la Mac):
`uv run raceengineer serve --demo` genera vueltas simuladas al pulsar Grabar.

## 6. Comandos manuales (pruebas)

La memoria compartida de AC solo existe **mientras estás en pista** (en el menú
principal no). Pon AC en modo ventana o ventana sin bordes para poder cambiar a
PowerShell con Alt+Tab sin problemas.

### 6a. Volcado crudo (para fixtures)

1. Abre AC, elige coche y circuito, y sal a pista (práctica).
2. Con Alt+Tab vuelve a PowerShell (en la carpeta `agent`) y ejecuta:

   ```powershell
   uv run raceengineer dump-raw --seconds 30
   ```

3. Vuelve al juego y conduce durante esos 30 segundos. Si puedes, pasa por boxes
   y pausa el juego unos segundos (Esc); así el volcado incluye esos estados.
4. Al terminar verás algo como
   `Volcado guardado en data\dumps\ac-20261016-201500.acraw.gz: ...`.

### 6b. Grabar vueltas desde la consola

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

   (cambia `N` por el número de la sesión). Los tiempos son los oficiales del
   juego. La columna "Tipo" dice si es vuelta de salida o entrada a boxes,
   lanzada (completa) o sin terminar (cortada con Ctrl+C), y "Fuera de pista"
   marca si en algún momento sacaste más de dos llantas.

### 6c. Comparar vueltas

```powershell
uv run raceengineer compare N 3
```

Compara la vuelta 3 de la sesión `N` con tu mejor vuelta limpia: diferencia
total, 10 tramos de pista y los lugares donde más tiempo pierdes. Con
`--ref 2` eliges la referencia, y con `--csv data\cmp.csv` guardas los datos
metro a metro para graficarlos en Excel.

### 6d. Dashboard web

```powershell
uv run raceengineer serve --lan
```

Muestra dos direcciones:

- `http://127.0.0.1:8000`: ábrela en el navegador de la PC.
- `http://192.168.x.x:8000`: ábrela en la Mac o el celular, conectados al mismo
  Wi-Fi o red de casa.

La primera vez, Windows pregunta si permites el acceso por el firewall: marca
**Redes privadas** y acepta. Sin `--lan`, el dashboard solo se ve desde la propia
PC. Para cerrarlo, pulsa Ctrl+C.

En el dashboard eliges una sesión, ves sus vueltas y pulsas **Comparar** para ver:

- el mapa del circuito pintado por tramos;
- las notas del ingeniero (frenadas, velocidad mínima, aceleración, bloqueos,
  patinadas, subviraje);
- las gráficas metro a metro contra tu mejor vuelta limpia;
- la tarjeta "Coche y neumáticos": presiones, temperaturas de cada llanta,
  reparto de frenada, TC y ABS.

Las sesiones grabadas antes de esta versión no tienen los datos del coche: graba
una nueva para verlos.

### Si algo falla

- `No se encontró la memoria compartida de Assetto Corsa`: AC no está en pista.
  Sal a pista y repite.
- La grabación termina sola: AC volvió al menú (estado OFF). Es lo esperado.
- Durante una repetición (replay) o en pausa no se graban muestras.

## 7. Enviar los resultados al Mac

### Sesiones grabadas

Para pasar una sesión a la Mac (para analizarla o usarla en pruebas):

```powershell
uv run raceengineer sessions
uv run raceengineer export-session N
```

(`N` es el número de la sesión). Crea `data\exports\sesion-N.rese.gz`; pesa
unos 11 MB por cada 10 minutos. Súbelo como archivo adjunto de una "release"
privada del repositorio, para no meterlo en el código. La primera vez, crea la
release:

```powershell
gh release create datos-sesiones --title "Sesiones para pruebas" --notes "Sesiones reales exportadas con export-session"
```

Y después, para cada sesión:

```powershell
gh release upload datos-sesiones data\exports\sesion-N.rese.gz
```

En la Mac se descarga con `gh release download datos-sesiones` y se añade con
`uv run raceengineer import-session sesion-N.rese.gz`.

### Volcados crudos

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
