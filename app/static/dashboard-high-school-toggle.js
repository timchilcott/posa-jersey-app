(function() {
  'use strict';

  if (typeof window.tableApp !== 'function' || window.tableApp.__highSchoolDashboardPatched) return;

  function playerPayload(player) {
    var payload = {
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
  }

  function insertToggle() {
    document.querySelectorAll('template').forEach(function(template) {
      if (template.content.querySelector('[x-model="selectedPlayer.isHighSchool"]')) return;

      var emailInput = template.content.querySelector('[x-model="selectedPlayer.email"]');
      if (!emailInput) return;

      var emailBlock = emailInput.closest('div');
      if (!emailBlock || !emailBlock.parentNode) return;

      var wrapper = document.createElement('div');
      wrapper.innerHTML = '' +
        '<label class="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3">' +
          '<input type="checkbox" x-model="selectedPlayer.isHighSchool" class="mt-0.5 rounded border-gray-300 text-pines-500 focus:ring-pines-500">' +
          '<span>' +
            '<span class="block text-sm font-medium text-gray-900">High School Player</span>' +
            '<span class="block text-xs text-gray-500">Uses the high school email template.</span>' +
          '</span>' +
        '</label>';
      emailBlock.parentNode.insertBefore(wrapper.firstElementChild, emailBlock.nextSibling);
    });
  }

  var originalTableApp = window.tableApp;
  window.tableApp = function() {
    var app = originalTableApp.apply(this, arguments);

    app.buildPlayerPayload = playerPayload;

    app.savePanel = async function() {
      try {
        var response = await fetch('/api/players/' + this.selectedPlayer.id, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.buildPlayerPayload(this.selectedPlayer))
        });
        var data = await response.json();
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
          var saveResponse = await fetch('/api/players/' + this.selectedPlayer.id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.buildPlayerPayload(this.selectedPlayer))
          });
          var saveData = await saveResponse.json();
          if (!saveData.success) {
            alert('Failed: ' + (saveData.error || 'Could not save player before sending email'));
            return;
          }
        }

        var response = await fetch('/api/admin/players/' + player.id + '/send-email', { method: 'POST' });
        var data = await response.json();
        if (data.success) {
          alert('Email sent to ' + player.email);
          await this.loadPlayers();
        } else {
          alert('Failed: ' + (data.message || data.error));
        }
      } catch (error) {
        console.error('Failed to send email:', error);
        alert('Failed to send email');
      }
    };

    return app;
  };

  window.tableApp.__highSchoolDashboardPatched = true;
  insertToggle();
})();