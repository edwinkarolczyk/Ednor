const toggleButton = document.querySelector('.menu-toggle');
const menu = document.querySelector('.menu');

if (toggleButton && menu) {
  toggleButton.addEventListener('click', () => {
    const isOpen = menu.classList.toggle('open');
    toggleButton.setAttribute('aria-expanded', String(isOpen));
  });
}
