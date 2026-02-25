/**
 * POSA Column Configuration Registry
 *
 * Central definition of all table columns per section.
 * Provides localStorage-based persistence for column visibility settings.
 * Load this script before the page's own <script> block.
 */
(function() {
  'use strict';

  var POSA_COLUMNS = {
    players: {
      key: 'posa_columns_players',
      columns: [
        { id: 'player', label: 'Player', default: true },
        { id: 'jersey', label: 'Jersey', default: true },
        { id: 'email', label: 'Email', default: true },
        { id: 'registrations', label: 'Registrations', default: true },
        { id: 'status', label: 'Status', default: true },
      ]
    },
    volunteers: {
      key: 'posa_columns_volunteers',
      columns: [
        { id: 'name', label: 'Name', default: true },
        { id: 'email', label: 'Email', default: true },
        { id: 'registration_type', label: 'Registration Type', default: true },
        { id: 'status', label: 'Status', default: true },
      ]
    },
    events: {
      key: 'posa_columns_events',
      columns: [
        { id: 'time', label: 'Time', default: true },
        { id: 'type', label: 'Type', default: true },
        { id: 'teams', label: 'Teams', default: true },
        { id: 'venue', label: 'Venue', default: true },
        { id: 'location', label: 'Location', default: true },
        { id: 'status', label: 'Status', default: true },
      ]
    },
    inventory: {
      key: 'posa_columns_inventory',
      columns: [
        { id: 'sport', label: 'Sport', default: true },
        { id: 'category', label: 'Category', default: true },
        { id: 'item', label: 'Item', default: true },
        { id: 'total', label: 'Total', default: true },
        { id: 'avail', label: 'Avail', default: true },
        { id: 'out', label: 'Out', default: true },
        { id: 'division', label: 'Division', default: false },
        { id: 'condition', label: 'Condition', default: true },
        { id: 'location', label: 'Location', default: true },
      ]
    },
    checked_out: {
      key: 'posa_columns_checked_out',
      columns: [
        { id: 'item', label: 'Item', default: true },
        { id: 'category', label: 'Category', default: true },
        { id: 'qty', label: 'Qty', default: true },
        { id: 'notes', label: 'Notes', default: true },
        { id: 'checked_out', label: 'Checked Out', default: true },
        { id: 'actions', label: 'Actions', default: true },
      ]
    },
    members: {
      key: 'posa_columns_members',
      columns: [
        { id: 'member', label: 'Member', default: true },
        { id: 'jersey', label: 'Jersey', default: true },
        { id: 'email', label: 'Email', default: true },
        { id: 'phone', label: 'Phone', default: true },
        { id: 'registrations', label: 'Registrations', default: true },
        { id: 'guardians', label: 'Guardians', default: true },
      ]
    },
  };

  // Map URL paths to section keys
  var pathMap = {
    '/admin/settings': 'players',
    '/admin/volunteers/settings': 'volunteers',
    '/inventory/settings': 'inventory',
    '/members/settings': 'members',
    '/events/settings': 'events',
    '/admin': 'players',
    '/admin/volunteers': 'volunteers',
    '/inventory': 'inventory',
    '/inventory/checked-out': 'checked_out',
    '/members': 'members',
    '/events': 'events',
  };

  POSA_COLUMNS.getSection = function(path) {
    return pathMap[path] || null;
  };

  POSA_COLUMNS.load = function(sectionKey) {
    var config = this[sectionKey];
    if (!config) return {};
    try {
      var stored = JSON.parse(localStorage.getItem(config.key));
      if (stored && typeof stored === 'object') return stored;
    } catch(e) { /* ignore parse errors */ }
    // Return defaults
    var defaults = {};
    config.columns.forEach(function(col) { defaults[col.id] = col.default; });
    return defaults;
  };

  POSA_COLUMNS.save = function(sectionKey, visibility) {
    var config = this[sectionKey];
    if (!config) return;
    localStorage.setItem(config.key, JSON.stringify(visibility));
  };

  POSA_COLUMNS.getDefaults = function(sectionKey) {
    var config = this[sectionKey];
    if (!config) return {};
    var defaults = {};
    config.columns.forEach(function(col) { defaults[col.id] = col.default; });
    return defaults;
  };

  window.POSA_COLUMNS = POSA_COLUMNS;
})();
