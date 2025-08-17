async function checkAuth() {
  const token = localStorage.getItem("token");
  if (!token) {
    // No token → redirect to login
    window.location.href = "login.html";
    return;
  }

  try {
    const res = await fetch("/me", {
      headers: { "Authorization": "Bearer " + token }
    });

    if (!res.ok) {
      // Invalid token → redirect
      localStorage.removeItem("token");
      window.location.href = "login.html";
      return;
    }

    const user = await res.json();
    console.log("Welcome", user.name, "| Visits:", user.visits);

    // You could show visit count in navbar
    const nav = document.querySelector("nav");
    const visitInfo = document.createElement("span");
    
    nav.appendChild(visitInfo);

  } catch (err) {
    localStorage.removeItem("token");
    window.location.href = "login.html";
  }
}

// Run on page load
document.addEventListener("DOMContentLoaded", checkAuth);
