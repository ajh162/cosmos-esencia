/* ============================================================
   COSMOS Y ESENCIA — JavaScript puro (sin librerías)

   1. El encabezado se vuelve sólido al bajar.
   2. Los bloques aparecen suavemente al entrar en pantalla,
      ahora EN CASCADA: los hijos entran uno tras otro.
   3. NUEVO — El banner del inicio se mueve más lento que el
      resto al hacer scroll (sensación de profundidad).
   4. NUEVO — Las portadas se inclinan siguiendo al cursor.
   5. NUEVO — Los botones de compra sueltan un pequeño estallido
      de chispas al presionarlos.
   6. El año del pie se actualiza solo.

   Todo lo que se mueve se apaga si la persona configuró su
   sistema para reducir animaciones.
   ============================================================ */

(function () {
  'use strict';

  var sinMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var esTactil = window.matchMedia('(hover: none)').matches;

  /* -- 1. Encabezado -------------------------------------- */
  var topbar = document.getElementById('topbar');

  function onScroll() {
    if (topbar) topbar.classList.toggle('is-stuck', window.scrollY > 40);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* -- 2. Aparición en cascada ----------------------------
     Antes todo el bloque aparecía de golpe. Ahora, dentro de
     cada bloque, los elementos principales entran con 90 ms de
     diferencia entre sí. Se siente escrito a mano en vez de
     encendido con un interruptor. */
  var bloques = document.querySelectorAll('.reveal');

  // A cada hijo directo relevante le asignamos su retraso
  function prepararCascada(bloque) {
    var hijos = bloque.querySelectorAll(
      ':scope > .eyebrow, :scope > h1, :scope > h2, :scope > h3, ' +
      ':scope > p, :scope > .btn, :scope > .specs, :scope > .buyline, ' +
      ':scope > .steps, :scope > blockquote, :scope > .book__body > *'
    );
    hijos.forEach(function (hijo, i) {
      hijo.style.setProperty('--retraso', (i * 90) + 'ms');
      hijo.classList.add('reveal');
    });
  }

  if (sinMovimiento || !('IntersectionObserver' in window)) {
    bloques.forEach(function (el) { el.classList.add('is-visible'); });
  } else {
    bloques.forEach(prepararCascada);

    var observador = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (entrada) {
        if (entrada.isIntersecting) {
          entrada.target.classList.add('is-visible');
          // Los hijos preparados arriba entran con su propio retraso
          entrada.target.querySelectorAll('.reveal').forEach(function (hijo) {
            hijo.classList.add('is-visible');
          });
          observador.unobserve(entrada.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

    // Solo observamos los bloques originales del HTML. A los hijos
    // los enciende su padre, y así respetan el orden de la cascada.
    bloques.forEach(function (el) { observador.observe(el); });
  }

  /* -- 3. Parallax del banner ------------------------------
     Escribimos --parallax y el CSS decide cuánto aplicar.
     requestAnimationFrame evita recalcular en cada píxel. */
  var banner = document.querySelector('.hero__banner');
  if (banner && !sinMovimiento) {
    var pendiente = false;

    window.addEventListener('scroll', function () {
      if (pendiente) return;
      pendiente = true;
      requestAnimationFrame(function () {
        var y = window.scrollY || 0;
        // Solo mientras el hero sigue a la vista: después no sirve de nada
        if (y < window.innerHeight * 1.2) {
          banner.style.setProperty('--parallax', (y * 0.18).toFixed(1) + 'px');
        }
        pendiente = false;
      });
    }, { passive: true });
  }

  /* -- 4. Portadas que siguen al cursor --------------------
     Escribimos --tiltX y --tiltY; el CSS los usa dentro del
     transform. En pantallas táctiles no se activa. */
  if (!sinMovimiento && !esTactil) {
    var GRADOS = 7;   // inclinación máxima. Súbelo para un efecto más marcado

    document.querySelectorAll('.book__cover').forEach(function (marco) {
      var img = marco.querySelector('img');
      if (!img) return;

      marco.addEventListener('pointermove', function (ev) {
        var caja = marco.getBoundingClientRect();
        // Posición del cursor dentro del marco, de -0.5 a 0.5
        var px = (ev.clientX - caja.left) / caja.width - 0.5;
        var py = (ev.clientY - caja.top) / caja.height - 0.5;

        img.style.setProperty('--tiltY', (px * GRADOS * 2).toFixed(2) + 'deg');
        img.style.setProperty('--tiltX', (-py * GRADOS * 2).toFixed(2) + 'deg');
      }, { passive: true });

      marco.addEventListener('pointerleave', function () {
        img.style.setProperty('--tiltY', '0deg');
        img.style.setProperty('--tiltX', '0deg');
      }, { passive: true });
    });
  }

  /* -- 5. Chispas al presionar comprar ---------------------
     Doce puntitos dorados que salen del botón y se apagan.
     Se crean y se destruyen solos: no dejan basura en el DOM.
     El enlace sigue funcionando igual; esto es puro adorno. */
  if (!sinMovimiento) {
    var estilo = document.createElement('style');
    estilo.textContent =
      '.chispa{position:fixed;width:5px;height:5px;border-radius:50%;' +
      'background:radial-gradient(circle,#FFF3D6,#E6B96C);pointer-events:none;' +
      'z-index:99;will-change:transform,opacity}';
    document.head.appendChild(estilo);

    document.querySelectorAll('.btn--solid').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        var caja = btn.getBoundingClientRect();
        var cx = caja.left + caja.width / 2;
        var cy = caja.top + caja.height / 2;

        for (var i = 0; i < 12; i++) {
          (function (indice) {
            var chispa = document.createElement('span');
            chispa.className = 'chispa';
            chispa.style.left = cx + 'px';
            chispa.style.top = cy + 'px';
            document.body.appendChild(chispa);

            var angulo = (Math.PI * 2 * indice) / 12 + Math.random() * 0.4;
            var distancia = 40 + Math.random() * 55;

            var finX = (Math.cos(angulo) * distancia).toFixed(1);
            var finY = (Math.sin(angulo) * distancia).toFixed(1);

            chispa.animate([
              { transform: 'translate(-50%,-50%) scale(1)', opacity: 1 },
              {
                transform: 'translate(calc(-50% + ' + finX + 'px), ' +
                           'calc(-50% + ' + finY + 'px)) scale(0)',
                opacity: 0
              }
            ], {
              duration: 620 + Math.random() * 260,
              easing: 'cubic-bezier(.2,.7,.3,1)'
            }).onfinish = function () { chispa.remove(); };
          })(i);
        }
      });
    });
  }

  /* -- 6. Año del pie -------------------------------------- */
  var year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();
})();
