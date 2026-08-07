(function() {
  'use strict';

  function showMessage(id) {
    var message = document.getElementById(id);
    if (!message) return;
    message.style.display = 'block';
    setTimeout(function() {
      message.style.display = 'none';
    }, 3000);
  }

  async function saveTemplate(config) {
    var subjectInput = document.getElementById(config.subjectId);
    var bodyInput = document.getElementById(config.bodyId);
    if (!subjectInput || !bodyInput) return;

    try {
      var response = await fetch('/email-templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: config.name,
          subject: subjectInput.value,
          body_html: bodyInput.value
        })
      });

      var data = await response.json().catch(function() { return {}; });
      if (!response.ok || data.success === false) {
        throw new Error(data.error || 'Failed to save template');
      }

      showMessage(config.successId);
    } catch (error) {
      console.error('Failed to save email template:', error);
      showMessage(config.errorId);
    }
  }

  function bindForm(config) {
    var form = document.getElementById(config.formId);
    if (!form || form.dataset.emailTemplateBound === 'true') return;

    form.dataset.emailTemplateBound = 'true';
    form.addEventListener('submit', function(event) {
      event.preventDefault();
      saveTemplate(config);
    });
  }

  function initEmailTemplateForms() {
    bindForm({
      formId: 'standard-form',
      subjectId: 'standard-subject',
      bodyId: 'standard-body',
      successId: 'standard-success',
      errorId: 'standard-error',
      name: 'standard_confirmation'
    });
    bindForm({
      formId: 'pines-form',
      subjectId: 'pines-subject',
      bodyId: 'pines-body',
      successId: 'pines-success',
      errorId: 'pines-error',
      name: 'pines_confirmation'
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEmailTemplateForms);
  } else {
    initEmailTemplateForms();
  }
})();