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

  // ── Font Awesome icons (loaded via <link> in each template <head>) ──
  const ICONS = {
    shirt: '<i class="fa-solid fa-shirt text-base"></i>',
    handshakeAngle: '<i class="fa-solid fa-handshake-angle text-base"></i>',
    goalNet: '<i class="fa-solid fa-goal-net text-base"></i>',
    users: '<i class="fa-solid fa-users text-base"></i>',
    calendar: '<i class="fa-regular fa-calendar-days text-base"></i>',
    arrowPath: '<i class="fa-solid fa-arrows-rotate text-base"></i>',
    envelope: '<i class="fa-regular fa-envelope text-base"></i>',
    gear: '<i class="fa-solid fa-gear text-base"></i>',
    bars3: '<i class="fa-solid fa-bars text-xl"></i>',
    xMark: '<i class="fa-solid fa-xmark text-xl"></i>',
  };

  // ── Navigation items ─────────────────────────────────────────────
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
    { label: 'Equipment', href: '/inventory', icon: ICONS.goalNet, match: ['/inventory'], children: [
      { label: 'All Equipment', href: '/inventory', childIcon: 'fa-solid fa-list' },
      { label: 'Checked Out', href: '/inventory/checked-out', childIcon: 'fa-solid fa-arrow-right-from-bracket' },
      { label: 'Add Item', href: '/inventory/add', childIcon: 'fa-solid fa-plus' },
      { label: 'Settings', href: '/inventory/settings', childIcon: 'fa-solid fa-gear' },
    ]},
    { label: 'Members', href: '/members', icon: ICONS.users, match: ['/members'], children: [
      { label: 'All Members', href: '/members', childIcon: 'fa-solid fa-list' },
      { label: 'Settings', href: '/members/settings', childIcon: 'fa-solid fa-gear' },
    ]},
    { label: 'Schedule', href: '/events', icon: ICONS.calendar, match: ['/events'], children: [
      { label: 'All Events', href: '/events', childIcon: 'fa-solid fa-list' },
      { label: 'Settings', href: '/events/settings', childIcon: 'fa-solid fa-gear' },
    ]},
  ];

  // ── Derive page title from the active child nav item for consistency ──
  function getPageTitle() {
    var active = getActiveSection();
    if (!active || !active.children) return '';
    for (var i = 0; i < active.children.length; i++) {
      if (isChildActive(active.children[i])) return active.children[i].label;
    }
    return '';
  }

  function isActive(item) {
    if (!item.match) return false;
    // Items with children: check if current path matches any child href
    if (item.children) {
      return item.children.some(function(c) { return isChildActive(c); });
    }
    return item.match.some(function(p) { return currentPath.startsWith(p); });
  }

  function isChildActive(child) {
    // Exact match for index pages (e.g., /inventory, /admin, /admin/volunteers)
    if (child.href === '/inventory' || child.href === '/admin' || child.href === '/admin/volunteers' ||
        child.href === '/members' || child.href === '/events') {
      return currentPath === child.href;
    }
    // Exact match for cross-section children (e.g., /email-templates under Players)
    if (child.href === '/email-templates' || child.href === '/sportsengine') {
      return currentPath === child.href || currentPath.startsWith(child.href + '/');
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
        ? 'bg-gray-100 posa-icon-active'
        : 'posa-icon hover:bg-gray-50';
      return '<a href="' + item.href + '" class="posa-rail-item relative flex items-center justify-center w-10 h-10 rounded-lg transition-colors ' + classes + '">' +
        item.icon +
        '<span class="posa-tooltip">' + item.label + '</span>' +
      '</a>';
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
    var html = '';

    // If the active section has children, show them as sub-navigation
    if (active && active.children && active.children.length > 0) {
      html += '<div class="space-y-0.5">';
      active.children.forEach(function(child) {
        var childActive = isChildActive(child);
        var childClasses = childActive
          ? 'bg-gray-100 text-pines-600 font-semibold'
          : 'text-gray-900 hover:bg-gray-50';
        var iconHtml = child.childIcon
          ? '<i class="' + child.childIcon + ' text-xs w-4 text-center mr-2 opacity-60"></i>'
          : '';
        html += '<a href="' + child.href + '" class="flex items-center px-3 py-2 rounded-lg text-sm transition-colors ' + childClasses + '">' + iconHtml + child.label + '</a>';
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
          var iconHtml = child.childIcon
            ? '<i class="' + child.childIcon + ' text-xs w-4 text-center mr-2 opacity-70"></i>'
            : '';
          html += '<a href="' + child.href + '" class="flex items-center px-3 py-1.5 rounded-lg text-xs transition-colors ' + childClasses + '">' + iconHtml + child.label + '</a>';
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

    var html = '' +
    '<aside id="posa-sidebar" class="hidden lg:flex bg-white h-screen flex-shrink-0 border-r border-gray-200" style="overflow:visible;z-index:20">' +
      '<!-- Icon Rail -->' +
      '<div class="posa-rail flex flex-col h-full">' +
        '<div class="flex items-center justify-center h-16 flex-shrink-0">' +
          '<img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-7">' +
        '</div>' +
        '<nav class="flex-1 flex flex-col items-center py-4 space-y-1 overflow-visible">' +
          buildRailItems() +
        '</nav>' +
      '</div>';

    // Always show nav panel — consistent width on every page
    html +=
    '<!-- Nav Panel -->' +
    '<div class="posa-nav-panel flex flex-col h-full">' +
      '<div class="flex items-center h-16 px-4 flex-shrink-0 border-b border-gray-100">' +
        '<span class="font-bold text-base text-gray-900">' + (active ? active.label : '') + '</span>' +
      '</div>' +
      '<nav class="flex-1 px-3 py-3 overflow-y-auto">' + panelContent + '</nav>' +
    '</div>';

    html += '</aside>';
    return html;
  }

  // ── Build page heading bar ─────────────────────────────────────────
  function buildPageHeading() {
    var title = getPageTitle();
    if (!title) return '';
    var active = getActiveSection();
    var iconHtml = active ? '<span class="text-pines-600 mr-2.5">' + active.icon + '</span>' : '';
    return '' +
    '<div class="bg-white border-b border-gray-200 px-6 py-4">' +
      '<h1 class="flex items-center text-lg font-bold text-gray-900">' + iconHtml + title + '</h1>' +
    '</div>';
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
    // Always same width: rail (3.5rem) + panel (12.5rem) = 16rem
    var style = document.createElement('style');
    style.textContent = '' +
      '#posa-sidebar { width: 16rem; }' +
      '#posa-sidebar .posa-rail { width: 3.5rem; flex-shrink: 0; overflow: visible; }' +
      '#posa-sidebar .posa-nav-panel { width: 12.5rem; flex-shrink: 0; border-left: 1px solid #e5e7eb; }' +
      /* Icon colors — use hex since Tailwind CDN can't resolve custom pines- classes in JS */
      '.posa-icon { color: #3C7939; }' +
      '.posa-icon:hover { color: #2f6130; }' +
      '.posa-icon-active { color: #2f6130; }' +
      /* Tooltips — appear on hover over rail icons */
      '.posa-tooltip {' +
        'display: none;' +
        'position: absolute;' +
        'left: calc(100% + 8px);' +
        'top: 50%;' +
        'transform: translateY(-50%);' +
        'background: #1f2937;' +
        'color: #fff;' +
        'font-size: 0.75rem;' +
        'padding: 4px 8px;' +
        'border-radius: 6px;' +
        'white-space: nowrap;' +
        'pointer-events: none;' +
        'z-index: 50;' +
      '}' +
      '.posa-rail-item:hover .posa-tooltip {' +
        'display: block;' +
      '}' +
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
          buildPageHeading() +
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
