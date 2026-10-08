// Optional Gmail launcher. Change this URL for a hosted deployment.
const INBOX2DONE_URL = 'http://localhost:8080';

if (!document.getElementById('inbox2done-launcher')) {
  const launcher = document.createElement('a');
  launcher.id = 'inbox2done-launcher';
  launcher.href = INBOX2DONE_URL;
  launcher.target = '_blank';
  launcher.rel = 'noopener noreferrer';
  launcher.textContent = 'Open Inbox2Done ↗';
  launcher.title = 'Open your Inbox2Done workspace to sync and analyze Gmail';
  Object.assign(launcher.style, {
    position: 'fixed', bottom: '24px', right: '24px', zIndex: '2147483647',
    background: '#24604f', color: 'white', padding: '12px 18px', borderRadius: '10px',
    textDecoration: 'none', font: '600 14px sans-serif', boxShadow: '0 3px 15px #0002',
  });
  document.body.appendChild(launcher);
}
