/* ============================================================
   COSMOS Y ESENCIA — cielo.js
   El cielo animado del fondo. JavaScript puro, sin librerías.

   Dibuja tres cosas dentro del <canvas id="cielo-estrellas">:
     1. Estrellas fijas que titilan (en 3 capas de profundidad)
     2. Un desplazamiento lento + parallax al hacer scroll
     3. Estrellas fugaces que cruzan cada cierto tiempo

   Cómo ajustarlo: todo lo que puedes cambiar está en AJUSTES,
   justo aquí abajo. No necesitas tocar nada más del archivo.
   ============================================================ */

(function () {
  'use strict';

  /* ═══════════════════ AJUSTES ═══════════════════════════════
     Sube o baja estos números para cambiar el ambiente.
     ══════════════════════════════════════════════════════════ */
  var AJUSTES = {
    // Cuántas estrellas por cada 10 000 píxeles de pantalla.
    // Más alto = cielo más poblado. Recomendado entre 0.8 y 2.5
    densidad: 1.5,

    // Tope de estrellas, para que en pantallas enormes no se trabe
    maximoEstrellas: 420,

    // Cada cuánto aparece una estrella fugaz (milisegundos, al azar entre los dos)
    fugazCadaMin: 3800,
    fugazCadaMax: 10000,

    // Cuánto se mueven las estrellas con el scroll (0 = nada, 1 = como el texto)
    parallax: 0.06
  };

  /* Colores de las estrellas, tomados de tu paleta de marca.
     La mayoría son marfil; unas pocas doradas y lavanda dan variedad. */
  var COLORES = [
    { rgb: '247,243,238', peso: 68 },  // marfil   #F7F3EE
    { rgb: '242,204,145', peso: 20 },  // oro claro #F2CC91
    { rgb: '185,168,214', peso: 12 }   // lavanda  #B9A8D6
  ];

  /* Las 3 capas: las lejanas son chicas, tenues y se mueven poco. */
  var CAPAS = [
    { proporcion: .58, radio: [0.4, 0.9], alfa: [.20, .48], deriva: 1.6, parallax: .35 },
    { proporcion: .30, radio: [0.7, 1.4], alfa: [.32, .70], deriva: 4.0, parallax: .70 },
    { proporcion: .12, radio: [1.1, 2.1], alfa: [.50, 1.0], deriva: 7.5, parallax: 1.0 }
  ];

  /* ═══════════════════ ARRANQUE ═══════════════════════════════ */

  var lienzo = document.getElementById('cielo-estrellas');
  if (!lienzo) return;                       // por si el div del cielo no existe
  var ctx = lienzo.getContext('2d');
  if (!ctx) return;                          // navegador muy viejo: se queda el fondo fijo

  var quietud = window.matchMedia('(prefers-reduced-motion: reduce)');

  var ancho = 0, alto = 0, dpr = 1;
  var estrellas = [];
  var fugaces = [];
  var proximaFugaz = 0;
  var tiempoAnterior = 0;
  var desplazamiento = 0;                    // cuánto ha bajado la página
  var animando = false;

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

    var total = Math.round((ancho * alto) / 10000 * AJUSTES.densidad);
    total = Math.min(total, AJUSTES.maximoEstrellas);

    CAPAS.forEach(function (capa) {
      var cuantas = Math.round(total * capa.proporcion);
      for (var i = 0; i < cuantas; i++) {
        estrellas.push({
          x: Math.random() * ancho,
          y: Math.random() * alto,
          r: azar(capa.radio[0], capa.radio[1]),
          alfa: azar(capa.alfa[0], capa.alfa[1]),
          color: colorAlAzar(),
          fase: Math.random() * Math.PI * 2,       // para que no titilen todas igual
          ritmo: azar(0.4, 1.5),                   // velocidad del titileo
          deriva: capa.deriva,                     // px por segundo hacia la derecha
          parallax: capa.parallax
        });
      }
    });
  }

  /* -- Ajustar el tamaño del lienzo ------------------------ */
  function medir() {
    // devicePixelRatio hace que se vea nítido en pantallas retina.
    // Lo topamos en 2 para no gastar de más en celulares.
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    ancho = lienzo.clientWidth;
    alto = lienzo.clientHeight;
    lienzo.width = Math.round(ancho * dpr);
    lienzo.height = Math.round(alto * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sembrarEstrellas();
  }

  /* -- Estrellas fugaces ----------------------------------- */
  function nuevaFugaz() {
    var haciaLaDerecha = Math.random() < 0.5;
    var velocidad = azar(620, 1000);                 // px por segundo
    var angulo = azar(0.30, 0.62);                   // inclinación en radianes (~17° a 35°)

    fugaces.push({
      x: haciaLaDerecha ? azar(-0.1, 0.55) * ancho : azar(0.45, 1.1) * ancho,
      y: azar(-0.05, 0.45) * alto,
      vx: (haciaLaDerecha ? 1 : -1) * Math.cos(angulo) * velocidad,
      vy: Math.sin(angulo) * velocidad,
      vida: 0,
      duracion: azar(700, 1150),
      largo: azar(0.10, 0.20)                        // qué tan larga es la cola
    });
  }

  function dibujarFugaz(f) {
    // La cola se dibuja como una línea que va del punto actual
    // hacia atrás, en dirección contraria al movimiento.
    var progreso = f.vida / f.duracion;
    var brillo = Math.sin(progreso * Math.PI);       // entra y sale suave
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

    // La cabecita luminosa
    var halo = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, 5);
    halo.addColorStop(0, 'rgba(255,251,244,' + (0.9 * brillo).toFixed(3) + ')');
    halo.addColorStop(1, 'rgba(242,204,145,0)');
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(f.x, f.y, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  /* -- Un cuadro de animación ------------------------------ */
  function dibujar(ahora) {
    if (!animando) return;

    var delta = tiempoAnterior ? Math.min(ahora - tiempoAnterior, 60) : 16;
    tiempoAnterior = ahora;
    var segundos = delta / 1000;
    var t = ahora / 1000;

    ctx.clearRect(0, 0, ancho, alto);

    // --- Estrellas ---
    for (var i = 0; i < estrellas.length; i++) {
      var e = estrellas[i];

      // Deriva horizontal continua (el cielo "gira" muy despacio)
      e.x += e.deriva * segundos;
      if (e.x > ancho + 3) e.x = -3;

      // Parallax: las capas cercanas se mueven más con el scroll
      var y = e.y - desplazamiento * AJUSTES.parallax * e.parallax;
      y = ((y % alto) + alto) % alto;                // envolver arriba/abajo

      // Titileo
      var titileo = e.alfa * (0.62 + 0.38 * Math.sin(t * e.ritmo + e.fase));

      ctx.fillStyle = 'rgba(' + e.color + ',' + titileo.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(e.x, y, e.r, 0, Math.PI * 2);
      ctx.fill();

      // Las estrellas grandes llevan un halo suave alrededor
      if (e.r > 1.3) {
        var g = ctx.createRadialGradient(e.x, y, 0, e.x, y, e.r * 4.5);
        g.addColorStop(0, 'rgba(' + e.color + ',' + (titileo * 0.30).toFixed(3) + ')');
        g.addColorStop(1, 'rgba(' + e.color + ',0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(e.x, y, e.r * 4.5, 0, Math.PI * 2);
        ctx.fill();
      }
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
      ctx.fillStyle = 'rgba(' + e.color + ',' + e.alfa.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(e.x, e.y, e.r, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  /* -- Encender / apagar ----------------------------------- */
  function encender() {
    if (animando) return;
    animando = true;
    tiempoAnterior = 0;
    proximaFugaz = performance.now() + 1200;
    requestAnimationFrame(dibujar);
  }

  function apagar() {
    animando = false;
  }

  function iniciar() {
    medir();
    if (quietud.matches) {
      // La persona pidió menos movimiento: cielo estrellado, pero quieto.
      apagar();
      dibujarQuieto();
    } else {
      encender();
    }
  }

  /* -- Eventos --------------------------------------------- */

  // Redimensionar con freno, para no rehacer el cielo en cada píxel
  var temporizador;
  window.addEventListener('resize', function () {
    clearTimeout(temporizador);
    temporizador = setTimeout(iniciar, 220);
  });

  // Posición del scroll (solo se guarda; el dibujo la usa después)
  window.addEventListener('scroll', function () {
    desplazamiento = window.scrollY || window.pageYOffset || 0;
  }, { passive: true });

  // Si la pestaña se va a segundo plano, paramos: no gastamos batería
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      apagar();
    } else if (!quietud.matches) {
      encender();
    }
  });

  // Si la persona cambia su preferencia de movimiento en el sistema
  if (quietud.addEventListener) {
    quietud.addEventListener('change', iniciar);
  }

  iniciar();
})();
