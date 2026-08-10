/* ============================================================
   COSMOS Y ESENCIA — JavaScript puro (sin librerías)
   Tres cosas, nada más:
   1. El encabezado se vuelve sólido al bajar.
   2. Los bloques aparecen suavemente al entrar en pantalla.
   3. El año del pie se actualiza solo.
   ============================================================ */

(function () {
  'use strict';

  /* -- 1. Encabezado -------------------------------------- */
  var topbar = document.getElementById('topbar');

  function onScroll() {
    topbar.classList.toggle('is-stuck', window.scrollY > 40);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* -- 2. Aparición al hacer scroll ------------------------ */
  var bloques = document.querySelectorAll('.reveal');
  var sinMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (sinMovimiento || !('IntersectionObserver' in window)) {
    // Si la persona pidió menos movimiento (o el navegador es viejo),
    // mostramos todo de inmediato.
    bloques.forEach(function (el) { el.classList.add('is-visible'); });
  } else {
    var observador = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (entrada) {
        if (entrada.isIntersecting) {
          entrada.target.classList.add('is-visible');
          observador.unobserve(entrada.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

    bloques.forEach(function (el) { observador.observe(el); });
  }

  /* -- 3. Año del pie -------------------------------------- */
  var year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();

  /* -- 4. (Opcional) Aviso si un botón de compra sigue vacío --
     Mientras no pegues tus links de Mercado Pago, el botón avisa
     en la consola en vez de recargar la página. Puedes borrar
     este bloque cuando ya tengas tus links puestos. */
  document.querySelectorAll('[data-producto]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      if (btn.getAttribute('href') === '#') {
        e.preventDefault();
        console.warn('Falta el link de Mercado Pago para: ' + btn.dataset.producto);
      }
    });
  });
})();
