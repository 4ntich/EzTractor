// Roda no <head> antes da página aparecer (evita piscar o tema errado). Padrão: Aero escuro.
export const THEME_BOOT_SCRIPT = `(function(){var d=document.documentElement;var t="aero",m="dark";
try{t=localStorage.getItem("ezt-theme")||t;m=localStorage.getItem("ezt-mode")||m;}catch(e){}
d.setAttribute("data-theme",t);d.setAttribute("data-mode",m);})();`;
