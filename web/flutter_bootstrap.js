{{flutter_js}}
{{flutter_build_config}}

const timeout = setTimeout(() => {
  const status = document.getElementById('load-status');
  if (status) status.innerHTML = 'Still loading. Check your connection, then <a href=".">reload Fieldwork</a>.';
}, 20000);
window.addEventListener('flutter-first-frame', () => {
  clearTimeout(timeout);
  document.getElementById('loading')?.remove();
});
_flutter.loader.load();
