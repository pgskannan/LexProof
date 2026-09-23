/*!
 * LexProof public verification widget.
 *
 * Embed a live "Verified by LexProof" badge for a piece of anchored
 * evidence on ANY third-party website (e.g. a counterparty's own site),
 * without any framework or build step. Usage:
 *
 *   <script src="https://YOUR-LEXPROOF-DOMAIN/lexproof-verify-widget.js"
 *           data-api-base="https://YOUR-LEXPROOF-API-DOMAIN" async></script>
 *   <div class="lexproof-verify" data-lexproof-evidence-id="EVIDENCE_ID"></div>
 *
 * `data-api-base` on the <script> tag is optional -- it defaults to the
 * script's own origin, which is correct whenever the widget script and the
 * LexProof API are served from the same domain. Set it explicitly if they
 * are not (e.g. the frontend and API live on different subdomains).
 *
 * Every div with a `data-lexproof-evidence-id` attribute anywhere on the
 * page is picked up automatically, both on initial load and whenever new
 * matching elements are added later (a MutationObserver watches for them,
 * which covers single-page apps that inject content after this script has
 * already run). Call `window.LexProofVerify.refresh()` to force an
 * immediate re-scan, e.g. right after inserting a new badge container.
 *
 * This script calls GET {apiBase}/api/verify/{evidenceId} -- a public,
 * unauthenticated, read-only endpoint that returns only cryptographic
 * hashes and blockchain metadata, never contract content. No cookies or
 * credentials are ever sent.
 */
(function () {
  'use strict';

  var ATTR = 'data-lexproof-evidence-id';
  var PROCESSED_ATTR = 'data-lexproof-processed';
  var LINK_ATTR = 'data-lexproof-verify-page';

  var STATUS_META = {
    VERIFIED: { label: 'Verified', color: '#059669', bg: '#ecfdf5', border: '#a7f3d0' },
    TAMPERED: { label: 'Tampered', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
    ANCHOR_NOT_FOUND: { label: 'Not yet anchored', color: '#b45309', bg: '#fffbeb', border: '#fde68a' },
    NOT_YET_ANCHORED: { label: 'Not yet anchored', color: '#b45309', bg: '#fffbeb', border: '#fde68a' },
    EVIDENCE_NOT_FOUND: { label: 'Evidence not found', color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb' },
  };
  var DEFAULT_STATUS_META = { label: 'Verification unavailable', color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb' };
  var LOADING_META = { label: 'Checking verification…', color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb' };

  function scriptApiBase() {
    var currentScript = document.currentScript;
    if (currentScript && currentScript.getAttribute('data-api-base')) {
      return currentScript.getAttribute('data-api-base').replace(/\/$/, '');
    }
    if (currentScript && currentScript.src) {
      try {
        return new URL(currentScript.src).origin;
      } catch (err) {
        /* fall through */
      }
    }
    return window.location.origin;
  }

  var apiBase = scriptApiBase();

  function el(tag, styles, text) {
    var node = document.createElement(tag);
    if (styles) {
      for (var key in styles) {
        if (Object.prototype.hasOwnProperty.call(styles, key)) node.style[key] = styles[key];
      }
    }
    if (text) node.textContent = text;
    return node;
  }

  function render(container, meta, linkUrl) {
    container.innerHTML = '';
    var badge = el('span', {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '4px 10px',
      borderRadius: '999px',
      border: '1px solid ' + meta.border,
      background: meta.bg,
      color: meta.color,
      fontFamily:
        '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif',
      fontSize: '13px',
      fontWeight: '600',
      lineHeight: '1.4',
    });
    var dot = el('span', {
      display: 'inline-block',
      width: '8px',
      height: '8px',
      borderRadius: '50%',
      background: meta.color,
      flexShrink: '0',
    });
    badge.appendChild(dot);
    badge.appendChild(document.createTextNode('LexProof: ' + meta.label));
    container.appendChild(badge);

    if (linkUrl) {
      var link = el('a', {
        display: 'inline-block',
        marginLeft: '8px',
        fontFamily:
          '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif',
        fontSize: '12px',
        color: '#2563eb',
        textDecoration: 'none',
      }, 'View full verification →');
      link.href = linkUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      container.appendChild(link);
    }
  }

  function verifyOne(container) {
    var evidenceId = container.getAttribute(ATTR);
    if (!evidenceId) return;
    container.setAttribute(PROCESSED_ATTR, 'true');
    render(container, LOADING_META, null);

    var url = apiBase + '/api/verify/' + encodeURIComponent(evidenceId);
    fetch(url)
      .then(function (response) {
        if (!response.ok) throw new Error('verify request failed: ' + response.status);
        return response.json();
      })
      .then(function (data) {
        var meta = STATUS_META[data.status] || DEFAULT_STATUS_META;
        var linkBase = container.getAttribute(LINK_ATTR);
        var linkUrl = linkBase
          ? linkBase.replace(/\/$/, '') + '?evidence_id=' + encodeURIComponent(evidenceId)
          : null;
        render(container, meta, linkUrl);
      })
      .catch(function () {
        render(container, DEFAULT_STATUS_META, null);
      });
  }

  function scan(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll('[' + ATTR + ']:not([' + PROCESSED_ATTR + '])');
    for (var i = 0; i < nodes.length; i += 1) {
      verifyOne(nodes[i]);
    }
  }

  function start() {
    scan(document);

    if (typeof MutationObserver !== 'undefined') {
      var observer = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i += 1) {
          var added = mutations[i].addedNodes;
          for (var j = 0; j < added.length; j += 1) {
            var node = added[j];
            if (node.nodeType !== 1) continue;
            if (node.hasAttribute && node.hasAttribute(ATTR)) verifyOne(node);
            if (node.querySelectorAll) scan(node);
          }
        }
      });
      observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  window.LexProofVerify = {
    refresh: function () {
      scan(document);
    },
  };
})();
