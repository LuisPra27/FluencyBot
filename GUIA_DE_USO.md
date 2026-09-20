# Guía de uso

Pasos para poner a funcionar el bot desde cero. El `README.md` explica
**cómo está hecho** y **por qué**; esta guía explica **cómo usarlo**.

---

## 1. Qué hace y qué NO hace

El bot entra a Rosetta Stone Fluency Builder, recorre tus cursos, busca las
lecciones con actividades pendientes y las resuelve con ayuda de una IA.

**Deja sin hacer una sola cosa a propósito: las actividades en las que hay
que hablar** (grabar tu voz con el micrófono). Todo lo demás —opción
múltiple, emparejar, llenar espacios, ordenar frases, escribir, escuchar
audios, vídeos, documentos, vocabulario— lo intenta resolver, y si falla y
Rosetta le enseña la respuesta, se la guarda para volver y responderla
bien.

No hace falta vigilarlo. Se reinicia solo si algo se rompe y para cuando no
queda nada pendiente.

---

## 2. Lo que necesitas antes de empezar

* **Una cuenta de Rosetta Stone Fluency Builder** (correo y contraseña).
* **La interfaz de Rosetta en español.** El bot busca textos literales
  ("Mis cursos", "Omitir", "Completa", "Omitida"...). Con la interfaz en
  inglés no funciona sin editar esos textos en `browser.py`.
* **Una API key de [build.nvidia.com](https://build.nvidia.com)** (gratuita).
  Es la IA que resuelve los ejercicios.
* **Python 3.10 o superior** y unos 500 MB libres (Chromium ocupa lo suyo).

---

## 3. Instalación

Desde la carpeta del proyecto, en PowerShell:

```powershell
python -m venv venv
```

```powershell
.\venv\Scripts\Activate.ps1
```

```powershell
pip install -r requirements.txt
```

```powershell
playwright install chromium
```

El último paso descarga el navegador que usa el bot. Sin él no arranca.

---

## 4. Credenciales

Crea un archivo llamado `.env` en la carpeta del proyecto:

```env
FLUENCY_EMAIL=tu_correo@ejemplo.com
FLUENCY_PASSWORD=tu_contraseña
AI_API_KEY=nvapi-...
```

Ese archivo **no se sube nunca a git** (está en `.gitignore`). Si falta
alguna de las tres variables, el bot se niega a arrancar y te dice cuál
falta.

---

## 5. Ejecutarlo

Con el entorno virtual activado:

```powershell
python -u bot.py
```

Si no lo activaste, llama al Python del entorno directamente:

```powershell
.\venv\Scripts\python.exe -u bot.py
```

> **El `-u` importa**: sin él la salida se queda en el buffer y, si paras
> el bot a mano, pierdes el log justo cuando más falta hace.
>
> **Y tiene que ser el Python del `venv`**, no el del sistema: el del
> sistema no tiene instaladas las dependencias y falla con
> `ModuleNotFoundError: No module named 'openai'`.

Se abre una ventana de Chromium y verás al bot trabajando. **No cierres esa
ventana ni uses ese navegador**: es el que está manejando.

Para pararlo: `Ctrl+C` en la terminal.

---

## 6. Cómo saber qué está pasando

Cada corrida escribe un log completo en `logs/bot_<fecha>_<hora>.log`, con
la hora al principio de cada línea. Es lo mismo que sale por pantalla, así
que puedes cerrar la terminal y revisarlo después.

Las líneas que conviene buscar:

| Línea | Qué significa |
| --- | --- |
| `Iniciando lección '...' [curso 11/31: ...]` | Empezó una lección nueva |
| `Respuesta ya conocida de este ejercicio` | Respondió de memoria, sin gastar IA |
| `Se agotaron los intentos; pulso "Mostrar respuesta"` | Falló, pero se aprendió la respuesta para la próxima |
| `respondidas de memoria` | Volvió a una actividad y colocó lo aprendido |
| `bloqueada definitivamente (solo queda voz)` | Lección terminada salvo hablar: es el resultado bueno |
| `quedó con N actividad(es) pendientes que NO son de voz` | Quedó trabajo sin hacer: eso sí es un problema |
| `Terminado de verdad` | No queda nada pendiente en ningún curso |

Para seguirlo en vivo desde otra terminal:

```powershell
Get-Content -Wait -Tail 20 (Get-ChildItem logs\*.log | Sort-Object LastWriteTime | Select-Object -Last 1)
```

---

## 7. Dejarlo corriendo toda la noche

Funciona sin problema, con una condición: **que el equipo no se suspenda**.
La pantalla puede apagarse y la sesión puede quedar bloqueada, pero si
Windows suspende, el bot muere.

```powershell
powercfg /change standby-timeout-ac 0
```

Para devolverlo a como estaba después (30 minutos, por ejemplo):

```powershell
powercfg /change standby-timeout-ac 30
```

Ten en cuenta que **el bot para solo cuando acaba**, no se queda dando
vueltas hasta la mañana. Si termina a las 3 am, a las 3 am se detiene y en
el log aparece `Terminado de verdad`.

Ante un error se reinicia solo, hasta 30 veces (`MAX_RESTARTS` en
`bot.py`). Cada reinicio vuelve a iniciar sesión y **no repite las lecciones
ya intentadas** en esa misma sesión, así que reintentar es barato.

---

## 8. Los archivos que va creando

Ninguno se sube a git: son el estado de *tu* cuenta.

| Archivo | Para qué sirve |
| --- | --- |
| `blocked_lessons.json` | Lecciones que no hay que volver a abrir (solo queda voz, ya resueltas, o agotaron sus reintentos) y por qué |
| `known_answers.json` | Respuestas que Rosetta le enseñó tras fallar. Se borran solas al usarlas con éxito |
| `speech_activities.json` | Actividades que, al abrirlas, resultaron exigir micrófono aunque su tipo no lo dijera |
| `logs/` | Un log por corrida |
| `debug_omits/` | Capturas de pantallas que no supo resolver. Solo para investigar; se pueden borrar |

**¿Cuándo borrarlos?** Casi nunca. Son los que hacen que la segunda corrida
sea mucho más rápida que la primera. Si sospechas que una lección quedó mal
marcada, borra **solo su entrada** de `blocked_lessons.json` en vez del
archivo entero.

---

## 9. Problemas comunes

**`ModuleNotFoundError: No module named 'openai'`**
Estás usando el Python del sistema. Activa el entorno o llama a
`.\venv\Scripts\python.exe`.

**`Falta FLUENCY_EMAIL en el archivo .env`**
No existe el `.env`, o está en otra carpeta, o le falta esa línea.

**Se abre el navegador pero no inicia sesión**
Revisa correo y contraseña entrando a mano en
[learn.rosettastone.com](https://learn.rosettastone.com). Si Rosetta pide
verificación, resuélvela una vez a mano y vuelve a lanzar el bot.

**Dice que todas las lecciones están bloqueadas y termina enseguida**
Es lo normal cuando ya no queda nada que no sea de voz. Míralo en el log:
`N lección(es) bloqueadas de verdad ... se omiten`.

**Se queda atascado en una actividad**
Un error en una actividad no tumba la lección: lo anota, guarda una captura
en `debug_omits/` y sigue con la siguiente. Si se repite siempre en la
misma, esa captura es por dónde empezar a mirar.

**La IA responde cualquier cosa o tarda mucho**
Puede ser la cuota de build.nvidia.com. En corridas largas conviene
revisarlo: en el log aparecen los errores de la API tal cual.

---

## 10. Si quieres compartirlo

El repositorio ya ignora todo lo personal (`.env`, los `.json` de estado,
`logs/`, capturas y `venv/`), así que se puede publicar tal cual. Quien lo
reciba solo tiene que hacer los pasos 2 a 5 de esta guía con **sus propias**
credenciales.

Dos cosas que conviene avisarle:

* Depende de que la interfaz de Rosetta esté **en español**.
* `requirements.txt` no fija versiones, así que una versión futura de
  Playwright podría romper algo.
