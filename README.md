# FluencyBot

FluencyBot es un bot de automatización desarrollado en Python que utiliza
Playwright e inteligencia artificial para resolver automáticamente ejercicios
de aprendizaje de idiomas en Rosetta Stone.

El bot navega por la plataforma, identifica los diferentes tipos de
actividades, utiliza modelos de IA para generar respuestas, las envía y
registra respuestas conocidas para utilizarlas posteriormente. Las actividades
que requieren respuesta hablada se omiten deliberadamente.

**FluencyBot no es una herramienta oficial de Rosetta Stone y no está
desarrollado, respaldado, autorizado ni afiliado a Rosetta Stone.**

---

## ⚠️ Advertencia importante

El uso de este software **puede infringir los términos de servicio, acuerdos de
licencia o reglas de uso de Rosetta Stone**. También puede estar prohibido por
las normas académicas de la institución o curso en el que se utilice.

El uso del bot puede provocar, entre otras cosas:

* Bloqueo o suspensión de la cuenta.
* Pérdida de acceso a Rosetta Stone.
* Pérdida del progreso realizado en la plataforma.
* Restricciones sobre la cuenta o el acceso al servicio.
* Consecuencias académicas si su utilización está prohibida por una
  institución educativa.
* Otras consecuencias derivadas de los términos, contratos o normas
  aplicables.

El autor no se responsabiliza por bloqueos, suspensiones, pérdida de acceso,
pérdida de progreso, sanciones académicas, restricciones de cuenta ni cualquier
otra consecuencia derivada del uso de este software.

La inclusión de esta advertencia no constituye asesoramiento jurídico ni
determina por sí misma si el uso del software es legal o ilegal. Las
consecuencias jurídicas dependen de la legislación, los contratos, las
licencias y las circunstancias aplicables en cada caso.

**Si decides utilizar FluencyBot, eres responsable de verificar previamente si
su uso está permitido y de asumir las consecuencias derivadas de dicho uso.**

---

## ¿Qué hace?

FluencyBot puede:

* Iniciar sesión en la plataforma.
* Detectar y clasificar diferentes tipos de actividades.
* Resolver preguntas mediante modelos de inteligencia artificial.
* Resolver actividades de selección múltiple.
* Resolver ejercicios de completar espacios.
* Resolver traducciones.
* Resolver ejercicios de ordenamiento.
* Resolver actividades de emparejamiento.
* Resolver actividades basadas en imágenes.
* Resolver preguntas escritas.
* Resolver actividades de comprensión auditiva.
* Registrar respuestas conocidas para reutilizarlas posteriormente.
* Reintentar actividades que no fueron resueltas correctamente.
* Omitir actividades que requieren respuesta hablada.

El comportamiento exacto puede variar dependiendo de la estructura actual de la
plataforma y de los modelos de IA utilizados.

**Tecnologías:** Python, Playwright, modelos de inteligencia artificial, y JSON
para el almacenamiento local de configuración y respuestas conocidas.

---

## Guía de uso

Pasos para poner a funcionar el bot desde cero. El `Progreso.md` explica
**cómo está hecho** y **por qué**; esta guía explica **cómo usarlo**.

---

### 1. Qué hace y qué NO hace

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

### 2. Lo que necesitas antes de empezar

* **Una cuenta de Rosetta Stone Fluency Builder** (correo y contraseña).
* **La interfaz de Rosetta en español.** El bot busca textos literales
  ("Mis cursos", "Omitir", "Completa", "Omitida"...). Con la interfaz en
  inglés no funciona sin editar esos textos en `browser.py`.
* **Una API key de [build.nvidia.com](https://build.nvidia.com)** (gratuita).
  Es la IA que resuelve los ejercicios.
* **Unos 500 MB libres** (Chromium ocupa lo suyo). Python 3.10 o superior
  también, pero si no lo tienes, `instalar.bat` te ofrece instalarlo.

---

### 3. Instalación

**Doble clic en `instalar.bat`.** Solo hace falta la primera vez.

Hace esto, en orden, y te dice en cada paso por dónde va:

1. Busca Python 3.10 o superior. Si no lo tienes, te pregunta si quieres
   instalarlo con `winget` (el instalador de programas de Windows).
2. Crea una carpeta `venv` con un Python propio para el bot. **No toca nada
   del resto del equipo**: para desinstalarlo basta con borrar la carpeta
   del bot.
3. Instala las librerías, en las versiones exactas con las que se ha
   probado.
4. Descarga el navegador que usa el bot.

Si prefieres saber exactamente qué ejecuta antes de abrirlo, ábrelo con el
Bloc de notas: es un archivo de texto.

> **¿Windows dice que el archivo puede ser peligroso?** Pasa con cualquier
> `.bat` descargado de internet. Pulsa "Más información" → "Ejecutar de
> todas formas". Si no te fías, ábrelo antes con el Bloc de notas y mira lo
> que hace.

<details>
<summary>Instalación a mano (sin el .bat)</summary>

Desde la carpeta del proyecto, en PowerShell:

```powershell
python -m venv venv
```

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

```powershell
.\venv\Scripts\python.exe -m playwright install chromium --no-shell
```

</details>

#### ¿Por qué no hay un `.exe`?

Se probó. Windows Defender lo borra a los pocos segundos de arrancar y lo
marca como `Trojan:Win32/Bearfoos.A!ml`. No es un virus: el `!ml` indica
una detección automática por "parecido", el falso positivo clásico de los
programas empaquetados con PyInstaller, sobre todo si descargan cosas,
abren un navegador y manejan contraseñas, que es justo lo que hace este.

Un `.exe` que el antivirus borra no le sirve a nadie. Los `.bat` son
texto: se pueden leer antes de ejecutarlos y no hay nada que marcar.

---

### 4. Credenciales

**La primera vez que abras `FluencyBot.bat`, el propio bot te las pide:**

```
Correo de Rosetta Stone: ...
Contraseña de Rosetta Stone (no se verá al escribir): ...
API key de build.nvidia.com (empieza por nvapi-): ...
```

La contraseña no se ve mientras la escribes; es normal. Se guardan en un
archivo `.env` dentro de la carpeta del bot y no vuelve a preguntarlas.

Si prefieres crearlo a mano, es un archivo de texto llamado `.env`:

```env
FLUENCY_EMAIL=tu_correo@ejemplo.com
FLUENCY_PASSWORD=tu_contraseña
AI_API_KEY=nvapi-...
```

Para cambiar algún dato, edita ese archivo o bórralo y el bot volverá a
preguntar. **Nunca lo compartas ni lo subas a ningún sitio**: tiene tu
contraseña en texto plano (en git ya está excluido por `.gitignore`).

---

### 5. Ejecutarlo

**Doble clic en `FluencyBot.bat`.**

Se abre una ventana de Chromium y verás al bot trabajando. **No cierres esa
ventana ni uses ese navegador**: es el que está manejando.

Para pararlo: cierra la ventana negra, o `Ctrl+C` dentro de ella. Cuando
termina solo, la ventana espera a que pulses una tecla para que puedas leer
cómo acabó.

<details>
<summary>Desde una terminal</summary>

```powershell
.\venv\Scripts\python.exe -u bot.py
```

* **El `-u` importa**: sin él la salida se queda en el buffer y, si paras el
  bot a mano, pierdes el log justo cuando más falta hace.
* **Tiene que ser el Python del `venv`**, no el del sistema: el del sistema
  no tiene las librerías y falla con
  `ModuleNotFoundError: No module named 'openai'`.

</details>

---

### 6. Cómo saber qué está pasando

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

### 7. Dejarlo corriendo toda la noche

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

### 8. Los archivos que va creando

Ninguno se sube a git: son el estado de *tu* cuenta.

| Archivo | Para qué sirve |
| --- | --- |
| `blocked_lessons.json` | Lecciones que no hay que volver a abrir (solo queda voz, ya resueltas, o agotaron sus reintentos) y por qué |
| `known_answers.json` | Respuestas que Rosetta le enseñó tras fallar. Se borran solas al usarlas con éxito |
| `speech_activities.json` | Actividades que, al abrirlas, resultaron exigir micrófono aunque su tipo no lo dijera |
| `.env` | Tus datos de acceso. Lo crea el bot la primera vez. **Tiene tu contraseña: no lo compartas** |
| `venv/` | El Python propio del bot, creado por `instalar.bat`. Si algo se estropea, bórrala y vuelve a instalar |
| `logs/` | Un log por corrida |
| `debug_omits/` | Capturas de pantallas que no supo resolver. Solo para investigar; se pueden borrar |

**¿Cuándo borrarlos?** Casi nunca. Son los que hacen que la segunda corrida
sea mucho más rápida que la primera. Si sospechas que una lección quedó mal
marcada, borra **solo su entrada** de `blocked_lessons.json` en vez del
archivo entero.

---

### 9. Problemas comunes

**"Todavía no está instalado: primero haz doble clic en instalar.bat"**
Falta la carpeta `venv`. Ejecuta `instalar.bat`.

**`ModuleNotFoundError: No module named 'openai'`**
Se está usando el Python del sistema en vez del del bot. Arranca siempre con
`FluencyBot.bat`; si ya lo hacías, vuelve a ejecutar `instalar.bat`.

**El instalador dice que no encuentra Python**
Deja que lo instale con `winget` (te lo pregunta), o descárgalo de
[python.org](https://www.python.org/downloads/) marcando **"Add python.exe
to PATH"**. Ojo: en muchos equipos, escribir `python` abre la Microsoft
Store en vez de ejecutar nada; el instalador lo detecta y no se deja
engañar.

**`Falta FLUENCY_EMAIL en el archivo .env`**
El bot no pudo preguntarte los datos (pasa si se lanza sin ventana, por
ejemplo desde el Programador de tareas). Ábrelo con doble clic en
`FluencyBot.bat`, o crea el `.env` a mano (sección 4).

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

### 9b. Si el modelo de IA deja de funcionar

Es el problema más probable a medio plazo: **NVIDIA da de baja modelos sin
avisar**. Ya pasó una vez con `muse-glimmer-30b`, que empezó a devolver 404
de un día para otro.

Hay tres redes de seguridad, en este orden:

1. **Al arrancar**, el bot comprueba que el modelo existe y lo dice en la
   primera línea del log:

   ```
   IA: modelo 'meta/llama-3.2-11b-vision-instruct' disponible
   ```

   Si ya no existe, no arranca (en vez de pasarse la noche respondiendo a
   ciegas) y te dice qué hacer.

2. **A mitad de corrida**, si desaparece, cambia solo a un sustituto y lo
   deja escrito en el log:

   ```
   !!! El modelo 'X' ya no existe; cambio a 'Y' para el resto de la corrida.
   ```

3. **A mano**, que es lo que querrás si ninguno de los sustitutos sirve.
   Pide la lista de lo que hay disponible ahora mismo:

   ```powershell
   .\venv\Scripts\python.exe ai.py
   ```

   Te imprime algo así, **probando cada candidato con una llamada real**:

   ```
   == Lo que hay configurado ahora en ai.py ==
     MODEL        meta/llama-3.2-11b-vision-instruct      disponible
     AUDIO_MODEL  nvidia/nemotron-3-nano-omni-30b-...     disponible

   == Sustitutos para MODEL, probados ahora mismo ==
     [RESPONDE]  meta/llama-3.2-11b-vision-instruct  (entiende imágenes)
     [RESPONDE]  nvidia/nemotron-3-super-120b-a12b
     [RESPONDE]  openai/gpt-oss-20b
     ...
   ```

   Coge uno que diga `[RESPONDE]`, abre `ai.py` y pégalo en la línea
   correspondiente de arriba del todo:

   ```python
   MODEL = "nvidia/nemotron-3-super-120b-a12b"
   AUDIO_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
   ```

   Si ninguno de esos responde, prueba el catálogo entero (tarda unos
   minutos, son más de 80 modelos):

   ```powershell
   .\venv\Scripts\python.exe ai.py todos
   ```

> **Por qué se prueban en vez de fiarse de la lista:** que un modelo
> aparezca en el catálogo de NVIDIA **no significa que funcione**. Probados
> los 82 ids el 2026-09-20, la mayoría devolvía error 404 al usarlos de
> verdad y algunos se quedaban colgados. Solo respondían cinco.
>
> **`MODEL` debería entender imágenes** (hay ejercicios de emparejar con
> fotos). Si eliges uno de solo texto, esos se responderán a ciegas y todo
> lo demás seguirá funcionando igual.

> Si te quedas sin modelo de audio no se rompe nada: esos ejercicios pasan a
> responderse a ciegas hasta que Rosetta enseña la respuesta, el bot se la
> guarda y la coloca en la siguiente pasada.

---

### 10. Si quieres compartirlo

El repositorio ya ignora todo lo personal (`.env`, los `.json` de estado,
`logs/`, capturas y `venv/`), así que se puede publicar tal cual. Quien lo
reciba solo tiene que hacer los pasos 2 a 5 de esta guía con **sus propias**
credenciales.

Solo necesita descargarlo, hacer doble clic en `instalar.bat` y después en
`FluencyBot.bat`.

Conviene avisarle de que depende de que la interfaz de Rosetta esté **en
español**.

Las versiones de las librerías están fijadas en `requirements.txt` (las
mismas con las que se ha probado), así que una actualización de Playwright o
de OpenAI no le romperá la instalación. Para probar versiones nuevas hay que
cambiarlas ahí a propósito.

---

## Seguridad

FluencyBot automatiza un navegador y puede interactuar con una cuenta en tu
nombre.

Por esta razón, no ejecutes código que no hayas revisado o comprendido y no
ignores automáticamente las advertencias de seguridad de Windows Defender u
otros sistemas de seguridad. Si un antivirus detecta algún archivo del
proyecto, analiza la detección antes de decidir si continuar: una detección
heurística puede ser un falso positivo, pero también puede indicar un
comportamiento que merece revisión.

Utiliza únicamente tus propias credenciales y revisa el código antes de
proporcionar cualquier información de acceso.

**No compartas nunca:**

* Tu contraseña.
* Tu archivo `.env`.
* Claves de API.
* Tokens de acceso.
* Cookies de sesión.
* Capturas de pantalla que contengan información sensible.
* Archivos de registro que puedan contener información privada.

---

## Contenido de Rosetta Stone

Este repositorio no tiene como objetivo redistribuir el contenido propietario
de Rosetta Stone.

El repositorio **no incluye deliberadamente**:

* Audios propietarios.
* Imágenes propietarias.
* Bases de datos de Rosetta Stone.
* Copias de las actividades.
* Materiales de los cursos.
* Credenciales de usuarios.
* Datos privados de otros usuarios.

El bot obtiene la información necesaria durante su ejecución directamente desde
la plataforma y utiliza modelos de IA para procesar las actividades.

---

## Uso académico

FluencyBot puede utilizarse para automatizar actividades que forman parte de
cursos o programas educativos.

Antes de utilizarlo con una actividad académica, verifica las reglas de tu
institución, profesor o programa. **El hecho de que técnicamente sea posible
automatizar una actividad no significa que su uso esté permitido
académicamente.**

---

## Estado del proyecto

Este proyecto es experimental y **puede dejar de funcionar** si Rosetta Stone
modifica su interfaz, estructura, mecanismos de autenticación, actividades o
cualquier otro componente utilizado por el bot.

No se garantiza que FluencyBot funcione permanentemente.

---

## Descargo de responsabilidad

El software se proporciona **tal como está**, sin garantía de funcionamiento
continuo, exactitud de las respuestas o compatibilidad futura.

El autor no se responsabiliza por:

* Bloqueos o suspensiones de cuentas.
* Pérdida de acceso.
* Pérdida de progreso.
* Errores producidos por el bot.
* Respuestas incorrectas generadas por la IA.
* Cambios realizados por Rosetta Stone que provoquen que el bot deje de
  funcionar.
* Sanciones académicas.
* Consecuencias derivadas del incumplimiento de términos de servicio,
  licencias, contratos o normas institucionales.
* Cualquier otra consecuencia derivada del uso del software.

El usuario decide bajo su propia responsabilidad si desea ejecutar este
proyecto.

---

## Afiliación

FluencyBot no está afiliado, asociado, patrocinado, respaldado ni autorizado
por Rosetta Stone.

Rosetta Stone y sus respectivas marcas y contenidos pertenecen a sus
correspondientes propietarios.

---

## Licencia

El código de FluencyBot se distribuye bajo la licencia MIT. Consulta el
archivo `LICENSE` incluido en este repositorio para conocer las condiciones
completas: en resumen, puedes usarlo, modificarlo y redistribuirlo mientras
conserves el aviso de copyright, y se entrega sin garantía de ningún tipo.

La licencia del código fuente no otorga derechos sobre contenidos, marcas,
servicios o propiedad intelectual pertenecientes a terceros.

---

## Autor

Luis Prado — proyecto desarrollado de forma independiente.
