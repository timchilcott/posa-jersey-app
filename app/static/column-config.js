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
        { id: 'player', label: 'Player', defaultOn: true },
        { id: 'jersey', label: 'Jersey', defaultOn: true },
        { id: 'email', label: 'Email', defaultOn: true },
        { id: 'registrations', label: 'Registrations', defaultOn: true },
        { id: 'status', label: 'Status', defaultOn: true },
      ]
    },
    volunteers: {
      key: 'posa_columns_volunteers',
      columns: [
        { id: 'name', label: 'Name', defaultOn: true },
        { id: 'email', label: 'Email', defaultOn: true },
        { id: 'registration_type', label: 'Registration Type', defaultOn: true },
        { id: 'status', label: 'Status', defaultOn: true },
      ]
    },
    events: {
      key: 'posa_columns_events',
      columns: [
        { id: 'time', label: 'Time', defaultOn: true },
        { id: 'type', label: 'Type', defaultOn: true },
        { id: 'teams', label: 'Teams', defaultOn: true },
        { id: 'venue', label: 'Venue', defaultOn: true },
        { id: 'location', label: 'Location', defaultOn: true },
        { id: 'status', label: 'Status', defaultOn: true },
      ]
    },
    inventory: {
      key: 'posa_columns_inventory',
      columns: [
        { id: 'sport', label: 'Sport', defaultOn: true },
        { id: 'category', label: 'Category', defaultOn: true },
        { id: 'item', label: 'Item', defaultOn: true },
        { id: 'total', label: 'Total', defaultOn: true },
        { id: 'avail', label: 'Avail', defaultOn: true },
        { id: 'out', label: 'Out', defaultOn: true },
        { id: 'division', label: 'Division', defaultOn: false },
        { id: 'condition', label: 'Condition', defaultOn: true },
        { id: 'location', label: 'Location', defaultOn: true },
      ]
    },
    checked_out: {
      key: 'posa_columns_checked_out',
      columns: [
        { id: 'item', label: 'Item', defaultOn: true },
        { id: 'category', label: 'Category', defaultOn: true },
        { id: 'qty', label: 'Qty', defaultOn: true },
        { id: 'notes', label: 'Notes', defaultOn: true },
        { id: 'checked_out', label: 'Checked Out', defaultOn: true },
        { id: 'actions', label: 'Actions', defaultOn: true },
      ]
    },
    members: {
      key: 'posa_columns_members',
      columns: [
        { id: 'member', label: 'Member', defaultOn: true },
        { id: 'jersey', label: 'Jersey', defaultOn: true },
        { id: 'email', label: 'Email', defaultOn: true },
        { id: 'phone', label: 'Phone', defaultOn: true },
        { id: 'registrations', label: 'Registrations', defaultOn: true },
        { id: 'guardians', label: 'Guardians', defaultOn: true },
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
    config.columns.forEach(function(col) { defaults[col.id] = col.defaultOn; });
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
    config.columns.forEach(function(col) { defaults[col.id] = col.defaultOn; });
    return defaults;
  };

  window.POSA_COLUMNS = POSA_COLUMNS;
})();
