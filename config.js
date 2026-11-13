/*
  Magic Layer settings (safe to edit, contains NO secrets).

  API_BASE: the address of your backend, for example "https://suno-saathi-magic.onrender.com".
            Leave it EMPTY ("") to run in offline demo mode: built-in rules and templates, no AI.
  You can also test a backend without editing this file by opening:   /magic/?api=https://your-backend
  (the address is then remembered in this browser; open /magic/?api= to forget it).

  NEVER put an API key here. Keys live only on the backend server.
*/
window.MAGIC_CONFIG = {
  API_BASE: "",
  DEFAULT_LANG: "en",
  REQUEST_TIMEOUT_MS: 20000   // free hosts can take ~1 minute to wake up the first time
};
