// Fill the forms' hidden csrf_token fields from the backend's
// double-submit cookie endpoint. If the backend is unreachable the
// fields stay empty and the backend's Origin check still applies.
fetch("/api/csrf", { credentials: "same-origin" })
  .then(function (r) { return r.json(); })
  .then(function (d) {
    document.querySelectorAll('input[name="csrf_token"]').forEach(function (i) {
      i.value = d.csrf_token;
    });
  })
  .catch(function () {});
