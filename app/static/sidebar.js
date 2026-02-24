/**
 * POSA Sidebar Component
 *
 * Self-injecting dual-panel sidebar navigation for all pages.
 * Include via <script src="/static/sidebar.js"></script> before </body>.
 *
 * Layout: Icon rail (56px) + Nav panel (200px) on desktop.
 * White background with green accent icons.
 * Mobile: hamburger menu with overlay.
 */
(function() {
  'use strict';

  // Skip sidebar on login page
  if (window.location.pathname === '/login') return;

  const currentPath = window.location.pathname;

  // ── Icon SVGs (Heroicons outline 24x24) ──────────────────────────
  const ICONS = {
    userGroup: '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z"/></svg>',
    handRaised: '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M10.05 4.575a1.575 1.575 0 10-3.15 0v3m3.15-3v-1.5a1.575 1.575 0 013.15 0v1.5m-3.15 0l.075 5.925m3.075-5.925v2.1a1.575 1.575 0 013.15 0V6m-3.15-.75V4.575m0 0a1.575 1.575 0 013.15 0V6m-3.15-.75v.75m6.3.75a1.575 1.575 0 00-1.575-1.575H16.2m3.15 3.15V12a6.3 6.3 0 01-6.3 6.3H9.45c-2.486 0-4.725-1.503-5.673-3.8l-.99-2.392a1.575 1.575 0 012.927-1.16l.626 1.513V4.575"/></svg>',
    cube: '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9"/></svg>',
    calendar: '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"/></svg>',
    arrowPath: '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M21.015 4.36v4.992"/></svg>',
    envelope: '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75"/></svg>',
    bars3: '<svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/></svg>',
    xMark: '<svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>',
  };

  // ── Navigation items ─────────────────────────────────────────────
  const NAV_ITEMS = [
    { label: 'Players', href: '/admin', icon: ICONS.userGroup, match: ['/admin'], children: [
      { label: 'All Players', href: '/admin' },
      { label: 'Add Player', href: '/admin/add' },
      { label: 'Sync Registrations', href: '/sportsengine' },
    ]},
    { label: 'Volunteers', href: '/admin/volunteers', icon: ICONS.handRaised, match: ['/admin/volunteers'] },
    { label: 'Inventory', href: '/inventory', icon: ICONS.cube, match: ['/inventory'], children: [
      { label: 'Equipment', href: '/inventory' },
      { label: 'Checked Out', href: '/inventory/checked-out' },
      { label: 'Add Item', href: '/inventory/add' },
    ]},
    { label: 'Events', href: '/events', icon: ICONS.calendar, match: ['/events'] },
    { type: 'divider' },
    { label: 'Email Templates', href: '/email-templates', icon: ICONS.envelope, match: ['/email-templates'] },
  ];

  function isActive(item) {
    if (!item.match) return false;
    // Items with children: check if current path matches any child href
    if (item.children) {
      return item.children.some(function(c) { return isChildActive(c); });
    }
    // Volunteers needs exact prefix match that doesn't collide with /admin
    if (item.href === '/admin/volunteers') return currentPath.startsWith('/admin/volunteers');
    return item.match.some(function(p) { return currentPath.startsWith(p); });
  }

  function isChildActive(child) {
    // Exact match for index pages (e.g., /inventory, /admin, /events)
    if (child.href === '/inventory' || child.href === '/admin' || child.href === '/events') {
      return currentPath === child.href;
    }
    return currentPath.startsWith(child.href);
  }

  // ── Build icon rail items ──────────────────────────────────────────
  function buildRailItems() {
    return NAV_ITEMS.map(function(item) {
      if (item.type === 'divider') {
        return '<div class="border-t border-gray-200 my-2 mx-2"></div>';
      }
      var active = isActive(item);
      var classes = active
        ? 'bg-gray-100 text-pines-600'
        : 'text-gray-400 hover:bg-gray-50 hover:text-pines-500';
      return '<a href="' + item.href + '" class="flex items-center justify-center w-10 h-10 rounded-lg transition-colors ' + classes + '" title="' + item.label + '">' +
        item.icon + '</a>';
    }).join('\n');
  }

  // ── Find the active section ────────────────────────────────────────
  function getActiveSection() {
    for (var i = 0; i < NAV_ITEMS.length; i++) {
      if (NAV_ITEMS[i].type === 'divider') continue;
      if (isActive(NAV_ITEMS[i])) return NAV_ITEMS[i];
    }
    return null;
  }

  // ── Build nav panel content (contextual for active section) ───────
  function buildPanelContent() {
    var active = getActiveSection();
    if (!active) return '';

    var html = '';

    // If the active section has children, show them as sub-navigation
    if (active.children && active.children.length > 0) {
      html += '<div class="space-y-0.5">';
      active.children.forEach(function(child) {
        var childActive = isChildActive(child);
        var childClasses = childActive
          ? 'bg-gray-100 text-pines-600 font-semibold'
          : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900';
        html += '<a href="' + child.href + '" class="block px-3 py-2 rounded-lg text-sm transition-colors ' + childClasses + '">' + child.label + '</a>';
      });
      html += '</div>';
    }

    return html;
  }

  // ── Build mobile nav items (icon + label, single column) ───────────
  function buildMobileNavItems() {
    return NAV_ITEMS.map(function(item) {
      if (item.type === 'divider') {
        return '<div class="border-t border-pines-400 my-3 mx-2"></div>';
      }
      var active = isActive(item);
      var classes = active
        ? 'bg-pines-600 text-white'
        : 'text-pines-100 hover:bg-pines-400 hover:text-white';

      var html = '<a href="' + item.href + '" class="flex items-center px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ' + classes + '" title="' + item.label + '">' +
        item.icon + '<span class="ml-3">' + item.label + '</span></a>';

      if (item.children && active) {
        html += '<div class="ml-8 mt-1 space-y-0.5">';
        item.children.forEach(function(child) {
          var childActive = isChildActive(child);
          var childClasses = childActive
            ? 'text-white font-semibold'
            : 'text-pines-200 hover:text-white';
          html += '<a href="' + child.href + '" class="block px-3 py-1.5 rounded-lg text-xs transition-colors ' + childClasses + '">' + child.label + '</a>';
        });
        html += '</div>';
      }

      return html;
    }).join('\n');
  }

  // ── Build full sidebar HTML (dual panel) ───────────────────────────
  function buildSidebarHTML() {
    var active = getActiveSection();
    var panelContent = buildPanelContent();
    var hasPanel = active && active.children && active.children.length > 0;

    var html = '' +
    '<aside id="posa-sidebar" class="hidden lg:flex bg-white h-screen flex-shrink-0 border-r border-gray-200">' +
      '<!-- Icon Rail -->' +
      '<div class="posa-rail flex flex-col h-full">' +
        '<div class="flex items-center justify-center h-16 flex-shrink-0">' +
          '<img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-7">' +
        '</div>' +
        '<nav class="flex-1 flex flex-col items-center py-4 space-y-1 overflow-y-auto">' +
          buildRailItems() +
        '</nav>' +
      '</div>';

    // Only show nav panel when active section has children
    if (hasPanel) {
      html +=
      '<!-- Nav Panel -->' +
      '<div class="posa-nav-panel flex flex-col h-full">' +
        '<div class="flex items-center h-16 px-4 flex-shrink-0 border-b border-gray-100">' +
          '<span class="font-semibold text-sm text-gray-900">' + active.label + '</span>' +
        '</div>' +
        '<nav class="flex-1 px-3 py-3 overflow-y-auto">' +
          panelContent +
        '</nav>' +
      '</div>';
    }

    html += '</aside>';
    return html;
  }

  // ── Build mobile top bar ─────────────────────────────────────────
  function buildMobileBar() {
    return '' +
    '<div id="posa-mobile-bar" class="lg:hidden flex items-center h-14 px-4 bg-white border-b border-gray-200 flex-shrink-0">' +
      '<button id="mobile-menu-btn" class="p-1.5 rounded-lg text-gray-600 hover:bg-gray-100">' +
        ICONS.bars3 +
      '</button>' +
      '<img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-6 ml-3">' +
      '<span class="ml-2 font-bold text-sm text-gray-900">POSA</span>' +
    '</div>';
  }

  // ── Build mobile overlay ─────────────────────────────────────────
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
          '<button id="mobile-close-btn" class="p-1.5 rounded-lg hover:bg-pines-400">' +
            ICONS.xMark +
          '</button>' +
        '</div>' +
        '<nav class="flex-1 px-2 py-4 space-y-1 overflow-y-auto">' +
          buildMobileNavItems() +
        '</nav>' +
      '</aside>' +
    '</div>';
  }

  // ── CSS ────────────────────────────────────────────────────────────
  function injectStyles() {
    var active = getActiveSection();
    var hasPanel = active && active.children && active.children.length > 0;
    var style = document.createElement('style');
    style.textContent = '' +
      '#posa-sidebar { width: ' + (hasPanel ? '16rem' : '3.5rem') + '; }' +
      '#posa-sidebar .posa-rail { width: 3.5rem; flex-shrink: 0; }' +
      '#posa-sidebar .posa-nav-panel { width: 12.5rem; flex-shrink: 0; border-left: 1px solid #e5e7eb; }' +
      /* Prevent FOUC */
      'body.sidebar-loading > *:not(script):not(style):not(link) { visibility: hidden; }' +
      'body.sidebar-ready > * { visibility: visible; }';
    document.head.appendChild(style);
  }

  // ── Main injection ───────────────────────────────────────────────
  function injectLayout() {
    var body = document.body;

    // Save page-specific Alpine attributes from body
    var xData = body.getAttribute('x-data') || '';
    var xInit = body.getAttribute('x-init') || '';
    var xCloak = body.hasAttribute('x-cloak');
    body.removeAttribute('x-data');
    body.removeAttribute('x-init');
    body.removeAttribute('x-cloak');

    // Remove old bg-gray-50 from body (content area handles it)
    body.classList.remove('bg-gray-50');
    body.style.overflow = 'hidden';
    body.style.height = '100vh';
    body.style.margin = '0';

    // Get existing page content
    var pageContent = body.innerHTML;

    // Build layout
    var layoutHTML = '' +
      '<div id="posa-layout" class="flex h-screen overflow-hidden">' +
        buildSidebarHTML() +
        '<div class="flex-1 flex flex-col overflow-hidden min-w-0">' +
          buildMobileBar() +
          '<main id="posa-content" class="flex-1 overflow-y-auto bg-gray-50"' +
            (xData ? ' x-data="' + xData.replace(/"/g, '&quot;') + '"' : '') +
            (xInit ? ' x-init="' + xInit.replace(/"/g, '&quot;') + '"' : '') +
            (xCloak ? ' x-cloak' : '') +
          '>' +
            pageContent +
          '</main>' +
        '</div>' +
      '</div>' +
      buildMobileOverlay();

    body.innerHTML = layoutHTML;
    body.classList.remove('sidebar-loading');
    body.classList.add('sidebar-ready');

    // ── Event listeners ────────────────────────────────────────────

    // Mobile menu open
    var mobileBtn = document.getElementById('mobile-menu-btn');
    var overlay = document.getElementById('posa-mobile-overlay');
    if (mobileBtn && overlay) {
      mobileBtn.addEventListener('click', function() {
        overlay.style.display = 'block';
      });
    }

    // Mobile menu close (backdrop or X button)
    var backdrop = document.getElementById('mobile-backdrop');
    var closeBtn = document.getElementById('mobile-close-btn');
    function closeMobile() {
      if (overlay) overlay.style.display = 'none';
    }
    if (backdrop) backdrop.addEventListener('click', closeMobile);
    if (closeBtn) closeBtn.addEventListener('click', closeMobile);

    // Close mobile menu when nav link clicked
    var mobileLinks = overlay ? overlay.querySelectorAll('a') : [];
    mobileLinks.forEach(function(link) {
      link.addEventListener('click', closeMobile);
    });
  }

  // ── Boot ─────────────────────────────────────────────────────────
  injectStyles();
  document.body.classList.add('sidebar-loading');

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectLayout);
  } else {
    injectLayout();
  }
})();
