// static/market/js/follow.js
// Follow/Unfollow functionality for authors

(function() {
  const followButtons = document.querySelectorAll(".follow-btn");
  
  if (!followButtons.length) return;

  // Load follow status for all buttons on page load
  followButtons.forEach((btn) => {
    // Skip disabled buttons (own items)
    if (btn.hasAttribute("disabled")) return;
    
    const authorId = parseInt(btn.dataset.authorId, 10);
    if (!authorId) return;

    loadFollowStatus(authorId, btn);

    // Handle click
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const isFollowing = btn.dataset.following === "true";
      
      if (isFollowing) {
        await unfollowAuthor(authorId, btn);
      } else {
        await followAuthor(authorId, btn);
      }
    });
  });

  async function loadFollowStatus(authorId, btn) {
    try {
      const res = await fetch(`/api/follow/status/${authorId}`, { credentials: "same-origin" });
      const data = await res.json();
      
      if (data.ok) {
        updateButton(btn, data.following);
        updateFollowersCount(authorId, data.followers_count);
      }
    } catch (err) {
      console.error("Failed to load follow status:", err);
    }
  }

  async function followAuthor(authorId, btn) {
    btn.disabled = true;
    try {
      const res = await fetch(`/api/follow/${authorId}`, { method: "POST", credentials: "same-origin" });
      const data = await res.json();
      
      if (data.ok) {
        updateButton(btn, data.following);
        updateFollowersCount(authorId, data.followers_count);
      } else if (data.error === "unauthorized") {
        // Redirect to login
        window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
      } else if (data.error === "self_follow") {
        // Self-follow: disable button permanently
        btn.disabled = true;
        btn.textContent = "Your model";
        btn.classList.add("self-follow");
      }
    } catch (err) {
      console.error("Failed to follow:", err);
    } finally {
      if (btn.textContent !== "Your model") {
        btn.disabled = false;
      }
    }
  }

  async function unfollowAuthor(authorId, btn) {
    btn.disabled = true;
    try {
      const res = await fetch(`/api/follow/${authorId}`, { method: "DELETE", credentials: "same-origin" });
      const data = await res.json();
      
      if (data.ok) {
        updateButton(btn, data.following);
        updateFollowersCount(authorId, data.followers_count);
      } else if (data.error === "unauthorized") {
        window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
      }
    } catch (err) {
      console.error("Failed to unfollow:", err);
    } finally {
      btn.disabled = false;
    }
  }

  function updateButton(btn, isFollowing) {
    btn.dataset.following = isFollowing ? "true" : "false";
    btn.textContent = isFollowing ? "Following" : "Follow";
    btn.classList.toggle("following", isFollowing);
  }

  function updateFollowersCount(authorId, count) {
    const counters = document.querySelectorAll(`.followers-count[data-author-id="${authorId}"]`);
    counters.forEach((el) => {
      el.textContent = count === 1 ? "1 follower" : `${count} followers`;
    });
  }
})();
