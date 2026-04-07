import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import PricingPage from "./pages/PricingPage";
import RecruiterDashboard from "./pages/RecruiterDashboard";
import "./index.css";

// Simple routing based on pathname
const currentPath = window.location.pathname;
const isRecruiterPage = currentPath === '/recruiter' || currentPath.startsWith('/recruiter/');
const isPricingPage = currentPath === '/pricing';

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      {isPricingPage ? <PricingPage /> : isRecruiterPage ? <RecruiterDashboard /> : <App />}
    </React.StrictMode>
  );
}
