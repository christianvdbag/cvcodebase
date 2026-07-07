document.querySelectorAll('.reveal').forEach((el, index) => {
  el.style.animationDelay = `${index * 120}ms`;
});
