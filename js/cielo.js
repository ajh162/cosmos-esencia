/* ============================================================
   COSMOS Y ESENCIA — cielo.js
   El cielo animado del fondo. JavaScript puro, sin librerías.

   Dibuja dentro del <canvas id="cielo-estrellas">:
     1. Estrellas fijas que titilan (en 3 capas de profundidad)
     2. Deriva lenta + parallax al hacer scroll
     3. Estrellas fugaces que cruzan cada cierto tiempo
     4. NUEVO — Constelaciones: líneas finísimas que unen estrellas
        cercanas y aparecen y desaparecen solas
     5. NUEVO — Polvo estelar: motas grandes y difuminadas que suben
        muy despacio, como partículas de luz en suspensión
     6. NUEVO — Destellos: de vez en cuando una estrella florece
        con cuatro rayos y se apaga
     7. NUEVO — El cursor ilumina: las estrellas cercanas al puntero
        brillan un poco más y se acercan entre sí

   Cómo ajustarlo: todo lo que puedes cambiar está en AJUSTES.
   Si algo se siente exagerado, baja el número y recarga.
   ============================================================ */

(function () {
  'use strict';

  /* ═══════════════════ AJUSTES ═══════════════════════════════ */
  var AJUSTES = {
    // Cuántas estrellas por cada 10 000 píxeles de pantalla.
    // Más alto = cielo más poblado. Recomendado entre 0.8 y 2.5
    densidad: 1.7,

    // Tope de estrellas, para que en pantallas enormes no se trabe
    maximoEstrellas: 460,

    // Cada cuánto aparece una estrella fugaz (ms, al azar entre los dos)
    fugazCadaMin: 3200,
    fugazCadaMax: 8500,

    // Cuánto se mueven las estrellas con el scroll (0 = nada, 1 = como el texto)
    parallax: 0.06,

    // — Constelaciones —
    // Distancia máxima (px) para que dos estrellas se unan con una línea
    constelacionDistancia: 132,
    // Opacidad máxima de esas líneas. Muy baja a propósito: se deben
    // intuir, no leer. Súbela a .16 si las quieres más presentes.
    constelacionAlfa: 0.10,

    // — Polvo estelar —
    polvoCantidad: 26,

    // — Destellos —
    destelloCadaMin: 2600,
    destelloCadaMax: 7000,

    // — Cursor —
    // Radio (px) en el que el puntero ilumina el cielo. 0 = desactivado
    radioCursor: 190
  };

  /* Colores de las estrellas, tomados de tu paleta de marca. */
  var COLORES = [
    { rgb: '247,243,238', peso: 66 },  // marfil    #F7F3EE
    { rgb: '242,204,145', peso: 21 },  // oro claro #F2CC91
    { rgb: '185,168,214', peso: 13 }   // lavanda   #B9A8D6
  ];

  /* Las 3 capas: las lejanas son chicas, tenues y se mueven poco. */
  var CAPAS = [
    { proporcion: .58, radio: [0.4, 0.9], alfa: [.20, .48], deriva: 1.6, parallax: .35 },
    { proporcion: .30, radio: [0.7, 1.4], alfa: [.32, .70], deriva: 4.0, parallax: .70 },
    { proporcion: .12, radio: [1.1, 2.1], alfa: [.50, 1.0], deriva: 7.5, parallax: 1.0 }
  ];

  /* ═══════════════════ ARRANQUE ═══════════════════════════════ */

  var lienzo = document.getElementById('cielo-estrellas');
  if (!lienzo) return;
  var ctx = lienzo.getContext('2d');
  if (!ctx) return;

  var quietud = window.matchMedia('(prefers-reduced-motion: reduce)');
  var esTactil = window.matchMedia('(hover: none)').matches;

  var ancho = 0, alto = 0, dpr = 1;
  var estrellas = [];
  var brillantes = [];        // subconjunto usado para las constelaciones
  var polvo = [];
  var fugaces = [];
  var destellos = [];
  var proximaFugaz = 0;
  var proximoDestello = 0;
  var tiempoAnterior = 0;
  var desplazamiento = 0;
  var animando = false;

  // Posición del cursor. -9999 = fuera de la pantalla
  var raton = { x: -9999, y: -9999 };

  function azar(min, max) { return min + Math.random() * (max - min); }

  function colorAlAzar() {
    var tirada = Math.random() * 100, suma = 0;
    for (var i = 0; i < COLORES.length; i++) {
      suma += COLORES[i].peso;
      if (tirada <= suma) return COLORES[i].rgb;
    }
    return COLORES[0].rgb;
  }

  /* -- Crear el cielo -------------------------------------- */
  function sembrarEstrellas() {
    estrellas = [];
    brillantes = [];

    var total = Math.round((ancho * alto) / 10000 * AJUSTES.densidad);
    total = Math.min(total, AJUSTES.maximoEstrellas);

    CAPAS.forEach(function (capa, indiceCapa) {
      var cuantas = Math.round(total * capa.proporcion);
      for (var i = 0; i < cuantas; i++) {
        var e = {
          x: Math.random() * ancho,
          y: Math.random() * alto,
          r: azar(capa.radio[0], capa.radio[1]),
          alfa: azar(capa.alfa[0], capa.alfa[1]),
          color: colorAlAzar(),
          fase: Math.random() * Math.PI * 2,
          ritmo: azar(0.4, 1.5),
          deriva: capa.deriva,
          parallax: capa.parallax,
          yDibujo: 0,                 // dónde quedó tras el parallax
          brilloActual: 0             // lo usa el efecto del cursor
        };
        estrellas.push(e);
        // Solo las estrellas de la capa más cercana forman constelaciones:
        // si se unieran todas, el cielo parecería una red de pescar.
        if (indiceCapa === 2) brillantes.push(e);
      }
    });
  }

  function sembrarPolvo() {
    polvo = [];
    var cuantas = Math.round(AJUSTES.polvoCantidad * Math.min(ancho / 1200, 1.4));
    for (var i = 0; i < cuantas; i++) {
      polvo.push({
        x: Math.random() * ancho,
        y: Math.random() * alto,
        r: azar(8, 26),                    // motas grandes y borrosas
        alfa: azar(.025, .075),
        subida: azar(4, 13),               // px por segundo hacia arriba
        vaiven: azar(6, 20),               // cuánto se mece de lado a lado
        fase: Math.random() * Math.PI * 2,
        ritmo: azar(.15, .45),
        color: Math.random() < .35 ? '242,204,145' : '185,168,214'
      });
    }
  }

  /* -- Ajustar el tamaño del lienzo ------------------------ */
  function medir() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    ancho = lienzo.clientWidth;
    alto = lienzo.clientHeight;
    lienzo.width = Math.round(ancho * dpr);
    lienzo.height = Math.round(alto * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sembrarEstrellas();
    sembrarPolvo();
  }

  /* -- Estrellas fugaces ----------------------------------- */
  function nuevaFugaz() {
    var haciaLaDerecha = Math.random() < 0.5;
    var velocidad = azar(620, 1000);
    var angulo = azar(0.30, 0.62);

    fugaces.push({
      x: haciaLaDerecha ? azar(-0.1, 0.55) * ancho : azar(0.45, 1.1) * ancho,
      y: azar(-0.05, 0.45) * alto,
      vx: (haciaLaDerecha ? 1 : -1) * Math.cos(angulo) * velocidad,
      vy: Math.sin(angulo) * velocidad,
      vida: 0,
      duracion: azar(700, 1150),
      largo: azar(0.10, 0.20)
    });
  }

  function dibujarFugaz(f) {
    var progreso = f.vida / f.duracion;
    var brillo = Math.sin(progreso * Math.PI);
    if (brillo <= 0) return;

    var colaX = f.x - f.vx * f.largo;
    var colaY = f.y - f.vy * f.largo;

    var degradado = ctx.createLinearGradient(f.x, f.y, colaX, colaY);
    degradado.addColorStop(0, 'rgba(247,243,238,' + (0.95 * brillo).toFixed(3) + ')');
    degradado.addColorStop(0.35, 'rgba(242,204,145,' + (0.45 * brillo).toFixed(3) + ')');
    degradado.addColorStop(1, 'rgba(242,204,145,0)');

    ctx.strokeStyle = degradado;
    ctx.lineWidth = 1.7;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(f.x, f.y);
    ctx.lineTo(colaX, colaY);
    ctx.stroke();

    var halo = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, 5);
    halo.addColorStop(0, 'rgba(255,251,244,' + (0.9 * brillo).toFixed(3) + ')');
    halo.addColorStop(1, 'rgba(242,204,145,0)');
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(f.x, f.y, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  /* -- NUEVO: destellos ------------------------------------
     Una estrella al azar "florece": crece un halo y le salen
     cuatro rayos finos, como los brillos de una foto nocturna. */
  function nuevoDestello() {
    if (!estrellas.length) return;
    var base = estrellas[Math.floor(Math.random() * estrellas.length)];
    destellos.push({
      x: base.x,
      y: base.yDibujo || base.y,
      vida: 0,
      duracion: azar(1400, 2400),
      tamano: azar(16, 34),
      color: Math.random() < .5 ? '242,204,145' : '247,243,238'
    });
  }

  function dibujarDestello(d) {
    var progreso = d.vida / d.duracion;
    var brillo = Math.sin(progreso * Math.PI);
    if (brillo <= 0) return;

    var largo = d.tamano * (0.5 + brillo * 0.9);

    // Los cuatro rayos
    ctx.strokeStyle = 'rgba(' + d.color + ',' + (0.42 * brillo).toFixed(3) + ')';
    ctx.lineWidth = 0.9;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(d.x - largo, d.y); ctx.lineTo(d.x + largo, d.y);
    ctx.moveTo(d.x, d.y - largo); ctx.lineTo(d.x, d.y + largo);
    ctx.stroke();

    // El corazón luminoso
    var halo = ctx.createRadialGradient(d.x, d.y, 0, d.x, d.y, largo * .55);
    halo.addColorStop(0, 'rgba(' + d.color + ',' + (0.85 * brillo).toFixed(3) + ')');
    halo.addColorStop(0.4, 'rgba(' + d.color + ',' + (0.20 * brillo).toFixed(3) + ')');
    halo.addColorStop(1, 'rgba(' + d.color + ',0)');
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(d.x, d.y, largo * .55, 0, Math.PI * 2);
    ctx.fill();
  }

  /* -- NUEVO: constelaciones -------------------------------
     Une con una línea las estrellas grandes que quedaron cerca.
     Cuanto más cerca, más visible la línea. Cerca del cursor,
     las líneas se refuerzan: el puntero "despierta" el cielo. */
  function dibujarConstelaciones() {
    var distMax = AJUSTES.constelacionDistancia;
    var distMax2 = distMax * distMax;

    for (var i = 0; i < brillantes.length; i++) {
      var a = brillantes[i];
      for (var j = i + 1; j < brillantes.length; j++) {
        var b = brillantes[j];
        var dx = a.x - b.x;
        var dy = a.yDibujo - b.yDibujo;
        var d2 = dx * dx + dy * dy;
        if (d2 > distMax2) continue;

        var cercania = 1 - Math.sqrt(d2) / distMax;
        var alfa = cercania * AJUSTES.constelacionAlfa;

        // Refuerzo por cursor: el punto medio del segmento decide
        if (AJUSTES.radioCursor > 0) {
          var mx = (a.x + b.x) / 2 - raton.x;
          var my = (a.yDibujo + b.yDibujo) / 2 - raton.y;
          var dCursor = Math.sqrt(mx * mx + my * my);
          if (dCursor < AJUSTES.radioCursor) {
            alfa += (1 - dCursor / AJUSTES.radioCursor) * 0.16;
          }
        }

        if (alfa <= 0.004) continue;

        ctx.strokeStyle = 'rgba(185,168,214,' + alfa.toFixed(4) + ')';
        ctx.lineWidth = 0.6;
        ctx.beginPath();
        ctx.moveTo(a.x, a.yDibujo);
        ctx.lineTo(b.x, b.yDibujo);
        ctx.stroke();
      }
    }
  }

  /* -- NUEVO: polvo estelar -------------------------------- */
  function dibujarPolvo(segundos, t) {
    for (var i = 0; i < polvo.length; i++) {
      var p = polvo[i];

      p.y -= p.subida * segundos;
      if (p.y < -p.r * 2) {              // al salir por arriba, reaparece abajo
        p.y = alto + p.r * 2;
        p.x = Math.random() * ancho;
      }

      var x = p.x + Math.sin(t * p.ritmo + p.fase) * p.vaiven;
      var y = p.y - desplazamiento * AJUSTES.parallax * 0.5;
      y = ((y % (alto + p.r * 4)) + alto + p.r * 4) % (alto + p.r * 4) - p.r * 2;

      var respiro = 0.75 + 0.25 * Math.sin(t * p.ritmo * 1.7 + p.fase);

      var g = ctx.createRadialGradient(x, y, 0, x, y, p.r);
      g.addColorStop(0, 'rgba(' + p.color + ',' + (p.alfa * respiro).toFixed(4) + ')');
      g.addColorStop(1, 'rgba(' + p.color + ',0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  /* -- Un cuadro de animación ------------------------------ */
  function dibujar(ahora) {
    if (!animando) return;

    var delta = tiempoAnterior ? Math.min(ahora - tiempoAnterior, 60) : 16;
    tiempoAnterior = ahora;
    var segundos = delta / 1000;
    var t = ahora / 1000;

    ctx.clearRect(0, 0, ancho, alto);

    // --- Polvo primero: va detrás de todo ---
    dibujarPolvo(segundos, t);

    // --- Estrellas ---
    for (var i = 0; i < estrellas.length; i++) {
      var e = estrellas[i];

      // Deriva horizontal continua (el cielo "gira" muy despacio)
      e.x += e.deriva * segundos;
      if (e.x > ancho + 3) e.x = -3;

      // Parallax: las capas cercanas se mueven más con el scroll
      var y = e.y - desplazamiento * AJUSTES.parallax * e.parallax;
      y = ((y % alto) + alto) % alto;
      e.yDibujo = y;                        // lo guardamos para las constelaciones

      // Titileo
      var titileo = e.alfa * (0.62 + 0.38 * Math.sin(t * e.ritmo + e.fase));

      // NUEVO — el cursor ilumina lo que tiene cerca
      var extra = 0;
      if (AJUSTES.radioCursor > 0 && raton.x > -9000) {
        var dx = e.x - raton.x, dy = y - raton.y;
        var d = Math.sqrt(dx * dx + dy * dy);
        if (d < AJUSTES.radioCursor) {
          extra = (1 - d / AJUSTES.radioCursor) * 0.55;
        }
      }
      // Suavizado: el brillo sube y baja poco a poco, no de golpe
      e.brilloActual += (extra - e.brilloActual) * Math.min(segundos * 6, 1);
      var alfaFinal = Math.min(titileo + e.brilloActual, 1);
      var radioFinal = e.r * (1 + e.brilloActual * 0.6);

      ctx.fillStyle = 'rgba(' + e.color + ',' + alfaFinal.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(e.x, y, radioFinal, 0, Math.PI * 2);
      ctx.fill();

      // Las estrellas grandes llevan un halo suave alrededor
      if (e.r > 1.3 || e.brilloActual > .12) {
        var radioHalo = radioFinal * 4.5;
        var g = ctx.createRadialGradient(e.x, y, 0, e.x, y, radioHalo);
        g.addColorStop(0, 'rgba(' + e.color + ',' + (alfaFinal * 0.30).toFixed(3) + ')');
        g.addColorStop(1, 'rgba(' + e.color + ',0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(e.x, y, radioHalo, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // --- Constelaciones (encima de las estrellas, debajo de los brillos) ---
    dibujarConstelaciones();

    // --- Destellos ---
    if (ahora > proximoDestello && destellos.length < 3) {
      nuevoDestello();
      proximoDestello = ahora + azar(AJUSTES.destelloCadaMin, AJUSTES.destelloCadaMax);
    }
    for (var k = destellos.length - 1; k >= 0; k--) {
      var d = destellos[k];
      d.vida += delta;
      dibujarDestello(d);
      if (d.vida >= d.duracion) destellos.splice(k, 1);
    }

    // --- Estrellas fugaces ---
    if (ahora > proximaFugaz && fugaces.length < 2) {
      nuevaFugaz();
      proximaFugaz = ahora + azar(AJUSTES.fugazCadaMin, AJUSTES.fugazCadaMax);
    }
    for (var j = fugaces.length - 1; j >= 0; j--) {
      var f = fugaces[j];
      f.vida += delta;
      f.x += f.vx * segundos;
      f.y += f.vy * segundos;
      dibujarFugaz(f);
      if (f.vida >= f.duracion) fugaces.splice(j, 1);
    }

    requestAnimationFrame(dibujar);
  }

  /* -- Versión quieta: se dibuja una sola vez -------------- */
  function dibujarQuieto() {
    ctx.clearRect(0, 0, ancho, alto);
    estrellas.forEach(function (e) {
      e.yDibujo = e.y;
      ctx.fillStyle = 'rgba(' + e.color + ',' + e.alfa.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(e.x, e.y, e.r, 0, Math.PI * 2);
      ctx.fill();
    });
    dibujarConstelaciones();
  }

  /* -- Encender / apagar ----------------------------------- */
  function encender() {
    if (animando) return;
    animando = true;
    tiempoAnterior = 0;
    proximaFugaz = performance.now() + 1200;
    proximoDestello = performance.now() + 900;
    requestAnimationFrame(dibujar);
  }

  function apagar() { animando = false; }

  function iniciar() {
    medir();
    if (quietud.matches) {
      apagar();
      dibujarQuieto();
    } else {
      encender();
    }
  }

  /* -- Eventos --------------------------------------------- */

  var temporizador;
  window.addEventListener('resize', function () {
    clearTimeout(temporizador);
    temporizador = setTimeout(iniciar, 220);
  });

  window.addEventListener('scroll', function () {
    desplazamiento = window.scrollY || window.pageYOffset || 0;
  }, { passive: true });

  // El cursor solo se sigue en equipos con puntero real. En celular
  // no aporta nada y sí gastaría batería.
  if (!esTactil && AJUSTES.radioCursor > 0) {
    window.addEventListener('pointermove', function (ev) {
      raton.x = ev.clientX;
      raton.y = ev.clientY;
    }, { passive: true });

    window.addEventListener('pointerleave', function () {
      raton.x = -9999; raton.y = -9999;
    }, { passive: true });
  }

  // Si la pestaña se va a segundo plano, paramos: no gastamos batería
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      apagar();
    } else if (!quietud.matches) {
      encender();
    }
  });

  if (quietud.addEventListener) {
    quietud.addEventListener('change', iniciar);
  }

  iniciar();
})();
