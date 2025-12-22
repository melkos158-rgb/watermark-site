window.__DEBUG_ERRORS__ = window.__DEBUG_ERRORS__ || [];
window.onerror = function(msg, url, line, col, err) {
  window.__DEBUG_ERRORS__.push({type:'onerror',msg,url,line,col,err});
};
window.onunhandledrejection = function(e) {
  window.__DEBUG_ERRORS__.push({type:'unhandledrejection',reason:e.reason});
};
const _origFetch = window.fetch;
window.fetch = function() {
  return _origFetch.apply(this, arguments).then(res => {
    if (!res.ok) {
      window.__DEBUG_ERRORS__.push({type:'fetch',url:res.url,status:res.status});
    }
    return res;
  }).catch(err => {
    window.__DEBUG_ERRORS__.push({type:'fetch-error',err});
    throw err;
  });
};
