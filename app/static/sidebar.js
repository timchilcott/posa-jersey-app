/**
 * POSA Sidebar Component
 *
 * Self-injecting dual-panel sidebar navigation for all pages.
 * Include via <script src="/static/sidebar.js"></script> before </body>.
 */
(function() {
  'use strict';

  if (window.location.pathname === '/login') return;

  const currentPath = window.location.pathname;

  const ICONS = {
    shirt: '<i class="fa-solid fa-shirt text-base"></i>',
    handshakeAngle: '<i class="fa-solid fa-handshake-angle text-base"></i>',
    futbol: '<i class="fa-solid fa-futbol text-base"></i>',
    users: '<i class="fa-solid fa-users text-base"></i>',
    trophy: '<i class="fa-solid fa-trophy text-base"></i>',
    clipboardCheck: '<i class="fa-solid fa-clipboard-check text-base"></i>',
    calendar: '<i class="fa-regular fa-calendar-days text-base"></i>',
    bars3: '<i class="fa-solid fa-bars text-xl"></i>',
    xMark: '<i class="fa-solid fa-xmark text-xl"></i>',
  };

  const NAV_ITEMS = [
    { label: 'Players', href: '/admin', icon: ICONS.shirt, match: ['/admin'], children: [
      { label: 'All Players', href: '/admin', childIcon: 'fa-solid fa-list' },
      { label: 'Add Player', href: '/admin/add', childIcon: 'fa-solid fa-plus' },
      { label: 'Sync Registrations', href: '/sportsengine', childIcon: 'fa-solid fa-arrows-rotate' },
      { label: 'Email Templates', href: '/email-templates', childIcon: 'fa-regular fa-envelope' },
      { label: 'Settings', href: '/admin/settings', childIcon: 'fa-solid fa-gear' },
    ]},
    { label: 'Volunteers', href: '/admin/volunteers', icon: ICONS.handshakeAngle, match: ['/admin/volunteers'], children: [
      { label: 'All Volunteers', href: '/admin/volunteers', childIcon: 'fa-solid fa-list' },
      { label: 'Settings', href: '/admin/volunteers/settings', childIcon: 'fa-solid fa-gear' },
    ]},
    { label: 'Equipment', href: '/inventory', icon: ICONS.futbol, match: ['/inventory'], children: [
      { label: 'All Equipment', href: '/inventory', childIcon: 'fa-solid fa-list' },
      { label: 'Checked Out', href: '/inventory/checked-out', childIcon: 'fa-solid fa-arrow-right-from-bracket' },
      { label: 'Add Item', href: '/inventory/add', childIcon: 'fa-solid fa-plus' },
      { label: 'Settings', href: '/inventory/settings', childIcon: 'fa-solid fa-gear' },
    ]},
    { label: 'Members', href: '/members', icon: ICONS.users, match: ['/members'], children: [
      { label: 'Directory', href: '/members', childIcon: 'fa-solid fa-address-book' },
      { label: 'Settings', href: '/members/settings', childIcon: 'fa-solid fa-gear' },
    ]},
    { label: 'Seasons', href: '/seasons', icon: ICONS.trophy, match: ['/seasons'], children: [
      { label: 'Teams & Rosters', href: '/seasons', childIcon: 'fa-solid fa-people-group' },
      { label: 'Standings', href: '/seasons/standings', childIcon: 'fa-solid fa-ranking-star' },
      { label: 'Settings', href: '/seasons/settings', childIcon: 'fa-solid fa-gear' },
    ]},
    { label: 'Evaluations', href: '/evaluations', icon: ICONS.clipboardCheck, match: ['/evaluations'], children: [
      { label: 'Evaluation Dashboard', href: '/evaluations', childIcon: 'fa-solid fa-clipboard-check' },
    ]},
    { label: 'Schedule', href: '/events', icon: ICONS.calendar, match: ['/events'], children: [
      { label: 'All Events', href: '/events', childIcon: 'fa-solid fa-list' },
      { label: 'Settings', href: '/events/settings', childIcon: 'fa-solid fa-gear' },
    ]},
  ];

  function isChildActive(child) {
    const exact = ['/inventory', '/admin', '/admin/volunteers', '/members', '/events', '/seasons', '/evaluations'];
    if (exact.includes(child.href)) return currentPath === child.href;
    if (child.href === '/email-templates' || child.href === '/sportsengine') {
      return currentPath === child.href || currentPath.startsWith(child.href + '/');
    }
    return currentPath.startsWith(child.href);
  }

  function isActive(item) {
    if (!item.match) return false;
    if (item.children) return item.children.some(isChildActive);
    return item.match.some(function(p) { return currentPath.startsWith(p); });
  }

  function getActiveSection() {
    for (let i = 0; i < NAV_ITEMS.length; i++) {
      if (isActive(NAV_ITEMS[i])) return NAV_ITEMS[i];
    }
    return null;
  }

  function getPageTitle() {
    const active = getActiveSection();
    if (!active || !active.children) return '';
    for (let i = 0; i < active.children.length; i++) {
      if (isChildActive(active.children[i])) return active.children[i].label;
    }
    return '';
  }

  function buildRailItems() {
    return NAV_ITEMS.map(function(item) {
      const active = isActive(item);
      const classes = active ? 'bg-gray-100 posa-icon-active' : 'posa-icon hover:bg-gray-50';
      return '<a href="' + item.href + '" class="posa-rail-item relative flex items-center justify-center w-10 h-10 rounded-lg transition-colors ' + classes + '">' +
        item.icon + '<span class="posa-tooltip">' + item.label + '</span></a>';
    }).join('\n');
  }

  function buildPanelContent() {
    const active = getActiveSection();
    let html = '';
    if (active && active.children && active.children.length > 0) {
      html += '<div class="space-y-0.5">';
      active.children.forEach(function(child) {
        const childActive = isChildActive(child);
        const childClasses = childActive ? 'bg-gray-100 text-pines-600 font-semibold' : 'text-gray-900 hover:bg-gray-50';
        const iconHtml = child.childIcon ? '<i class="' + child.childIcon + ' text-xs w-4 text-center mr-2 opacity-60"></i>' : '';
        html += '<a href="' + child.href + '" class="flex items-center px-3 py-2 rounded-lg text-sm transition-colors ' + childClasses + '">' + iconHtml + child.label + '</a>';
      });
      html += '</div>';
    }
    return html;
  }

  function buildMobileNavItems() {
    return NAV_ITEMS.map(function(item) {
      const active = isActive(item);
      const classes = active ? 'bg-pines-600 text-white' : 'text-pines-100 hover:bg-pines-400 hover:text-white';
      let html = '<a href="' + item.href + '" class="flex items-center px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ' + classes + '" title="' + item.label + '">' +
        item.icon + '<span class="ml-3">' + item.label + '</span></a>';
      if (item.children && active) {
        html += '<div class="ml-8 mt-1 space-y-0.5">';
        item.children.forEach(function(child) {
          const childActive = isChildActive(child);
          const childClasses = childActive ? 'text-white font-semibold' : 'text-pines-200 hover:text-white';
          const iconHtml = child.childIcon ? '<i class="' + child.childIcon + ' text-xs w-4 text-center mr-2 opacity-70"></i>' : '';
          html += '<a href="' + child.href + '" class="flex items-center px-3 py-1.5 rounded-lg text-xs transition-colors ' + childClasses + '">' + iconHtml + child.label + '</a>';
        });
        html += '</div>';
      }
      return html;
    }).join('\n');
  }

  function buildSidebarHTML() {
    const active = getActiveSection();
    return '' +
      '<aside id="posa-sidebar" class="hidden lg:flex bg-white h-screen flex-shrink-0 border-r border-gray-200" style="overflow:visible;z-index:20">' +
        '<div class="posa-rail flex flex-col h-full">' +
          '<div class="flex items-center justify-center h-16 flex-shrink-0">' +
            '<img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-7">' +
          '</div>' +
          '<nav class="flex-1 flex flex-col items-center py-4 space-y-1 overflow-visible">' + buildRailItems() + '</nav>' +
        '</div>' +
        '<div class="posa-nav-panel flex flex-col h-full">' +
          '<div class="flex items-center h-16 px-4 flex-shrink-0 border-b border-gray-100">' +
            '<span class="font-bold text-base text-gray-900">' + (active ? active.label : '') + '</span>' +
          '</div>' +
          '<nav class="flex-1 px-3 py-3 overflow-y-auto">' + buildPanelContent() + '</nav>' +
        '</div>' +
      '</aside>';
  }

  function buildPageHeading() {
    const title = getPageTitle();
    if (!title) return '';
    const active = getActiveSection();
    let iconHtml = '';
    if (active && active.children) {
      for (let i = 0; i < active.children.length; i++) {
        if (isChildActive(active.children[i]) && active.children[i].childIcon) {
          iconHtml = '<span class="text-pines-600 mr-2.5"><i class="' + active.children[i].childIcon + ' text-base"></i></span>';
          break;
        }
      }
    }
    return '<div class="bg-white border-b border-gray-200 px-6 py-4"><h1 class="flex items-center text-lg font-bold text-gray-900">' + iconHtml + title + '</h1></div>';
  }

  function buildMobileBar() {
    return '' +
      '<div id="posa-mobile-bar" class="lg:hidden flex items-center h-14 px-4 bg-white border-b border-gray-200 flex-shrink-0">' +
        '<button id="mobile-menu-btn" class="p-1.5 rounded-lg text-gray-600 hover:bg-gray-100">' + ICONS.bars3 + '</button>' +
        '<img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-6 ml-3">' +
        '<span class="ml-2 font-bold text-sm text-gray-900">POSA</span>' +
      '</div>';
  }

  function buildMobileOverlay() {
    return '' +
      '<div id="posa-mobile-overlay" class="fixed inset-0 z-40 lg:hidden" style="display:none">' +
        '<div id="mobile-backdrop" class="fixed inset-0 bg-black/50"></div>' +
        '<aside class="fixed inset-y-0 left-0 w-64 bg-pines-500 text-white z-50 flex flex-col">' +
          '<div class="flex items-center justify-between h-14 px-4 border-b border-pines-400">' +
            '<div class="flex items-center">' +
              '<img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-7 brightness-0 invert">' +
              '<span class="ml-3 font-bold text-lg">POSA</span>' +
            '</div>' +
            '<button id="mobile-close-btn" class="p-1.5 rounded-lg hover:bg-pines-400">' + ICONS.xMark + '</button>' +
          '</div>' +
          '<nav class="flex-1 px-2 py-4 space-y-1 overflow-y-auto">' + buildMobileNavItems() + '</nav>' +
        '</aside>' +
      '</div>';
  }

  function injectStyles() {
    const style = document.createElement('style');
    style.textContent = '' +
      '#posa-sidebar { width: 16rem; }' +
      '#posa-sidebar .posa-rail { width: 3.5rem; flex-shrink: 0; overflow: visible; }' +
      '#posa-sidebar .posa-nav-panel { width: 12.5rem; flex-shrink: 0; border-left: 1px solid #e5e7eb; }' +
      '.posa-icon { color: #3C7939; }' +
      '.posa-icon:hover { color: #2f6130; }' +
      '.posa-icon-active { color: #2f6130; }' +
      '.posa-tooltip { display:none; position:absolute; left:calc(100% + 8px); top:50%; transform:translateY(-50%); background:#1f2937; color:#fff; font-size:0.75rem; padding:4px 8px; border-radius:6px; white-space:nowrap; pointer-events:none; z-index:50; }' +
      '.posa-rail-item:hover .posa-tooltip { display:block; }' +
      'body.sidebar-loading > *:not(script):not(style):not(link) { visibility: hidden; }' +
      'body.sidebar-ready > * { visibility: visible; }';
    document.head.appendChild(style);
  }

  function isAdminDashboard() {
    return currentPath === '/admin';
  }

  function installAdminHighSchoolTogglePatch() {
    if (!isAdminDashboard() || typeof window.tableApp !== 'function' || window.tableApp.__highSchoolTogglePatched) return;

    const originalTableApp = window.tableApp;
    const patchedTableApp = function() {
      const app = originalTableApp.apply(this, arguments);

      app.buildPlayerPayload = function(player) {
        const payload = {
          full_name: player.name,
          parent_email: player.email,
          jersey_number: player.jersey,
          is_high_school: !!player.isHighSchool
        };
        if (player.dateOfBirth) {
          payload.date_of_birth = player.dateOfBirth;
        } else {
          payload.birth_year = player.birthYear || null;
        }
        return payload;
      };

      app.savePanel = async function() {
        try {
          const response = await fetch(`/api/players/${this.selectedPlayer.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.buildPlayerPayload(this.selectedPlayer))
          });
          const data = await response.json();
          if (data.success) {
            await this.loadPlayers();
            this.closePanel();
          }
        } catch (error) {
          console.error('Failed to update player:', error);
          alert('Failed to update player');
        }
      };

      app.sendEmail = async function(player) {
        try {
          if (this.selectedPlayer && this.selectedPlayer.id === player.id) {
            const saveResponse = await fetch(`/api/players/${this.selectedPlayer.id}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.buildPlayerPayload(this.selectedPlayer))
            });
            const saveData = await saveResponse.json();
            if (!saveData.success) {
              alert(`Failed: ${saveData.error || 'Could not save player before sending email'}`);
              return;
            }
          }

          const response = await fetch(`/api/admin/players/${player.id}/send-email`, { method: 'POST' });
          const data = await response.json();
          if (data.success) {
            alert(`Email sent to ${player.email}`);
            await this.loadPlayers();
          } else {
            alert(`Failed: ${data.message || data.error}`);
          }
        } catch (error) {
          console.error('Failed to send email:', error);
          alert('Failed to send email');
        }
      };

      return app;
    };

    patchedTableApp.__highSchoolTogglePatched = true;
    window.tableApp = patchedTableApp;
  }

  function insertAdminHighSchoolToggle() {
    if (!isAdminDashboard()) return;

    document.querySelectorAll('template').forEach(function(template) {
      if (template.content.querySelector('[x-model="selectedPlayer.isHighSchool"]')) return;

      const emailInput = template.content.querySelector('[x-model="selectedPlayer.email"]');
      if (!emailInput) return;

      const emailBlock = emailInput.closest('div');
      if (!emailBlock || !emailBlock.parentNode) return;

      const wrapper = document.createElement('div');
      wrapper.innerHTML = '' +
        '<label class="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3">' +
          '<input type="checkbox" x-model="selectedPlayer.isHighSchool" class="rounded border-gray-300 text-pines-500 focus:ring-pines-500">' +
          '<span class="text-sm font-medium text-gray-900">High School Player</span>' +
        '</label>';
      emailBlock.parentNode.insertBefore(wrapper.firstElementChild, emailBlock.nextSibling);
    });
  }

  function injectLayout() {
    const body = document.body;
    const xData = body.getAttribute('x-data') || '';
    const xInit = body.getAttribute('x-init') || '';
    const xCloak = body.hasAttribute('x-cloak');
    body.removeAttribute('x-data');
    body.removeAttribute('x-init');
    body.removeAttribute('x-cloak');
    body.classList.remove('bg-gray-50');
    body.style.overflow = 'hidden';
    body.style.height = '100vh';
    body.style.margin = '0';

    const pageContent = body.innerHTML;
    const layoutHTML = '' +
      '<div id="posa-layout" class="flex h-screen overflow-hidden">' +
        buildSidebarHTML() +
        '<div class="flex-1 flex flex-col overflow-hidden min-w-0">' +
          buildMobileBar() +
          buildPageHeading() +
          '<main id="posa-content" class="flex-1 overflow-y-auto bg-gray-50"' +
            (xData ? ' x-data="' + xData.replace(/"/g, '&quot;') + '"' : '') +
            (xInit ? ' x-init="' + xInit.replace(/"/g, '&quot;') + '"' : '') +
            (xCloak ? ' x-cloak' : '') +
          '>' + pageContent + '</main>' +
        '</div>' +
      '</div>' + buildMobileOverlay();

    body.innerHTML = layoutHTML;
    insertAdminHighSchoolToggle();
    body.classList.remove('sidebar-loading');
    body.classList.add('sidebar-ready');

    const mobileBtn = document.getElementById('mobile-menu-btn');
    const overlay = document.getElementById('posa-mobile-overlay');
    if (mobileBtn && overlay) mobileBtn.addEventListener('click', function() { overlay.style.display = 'block'; });

    const backdrop = document.getElementById('mobile-backdrop');
    const closeBtn = document.getElementById('mobile-close-btn');
    function closeMobile() { if (overlay) overlay.style.display = 'none'; }
    if (backdrop) backdrop.addEventListener('click', closeMobile);
    if (closeBtn) closeBtn.addEventListener('click', closeMobile);
    const mobileLinks = overlay ? overlay.querySelectorAll('a') : [];
    mobileLinks.forEach(function(link) { link.addEventListener('click', closeMobile); });
  }

  installAdminHighSchoolTogglePatch();
  injectStyles();
  document.body.classList.add('sidebar-loading');
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectLayout);
  } else {
    injectLayout();
  }
})();