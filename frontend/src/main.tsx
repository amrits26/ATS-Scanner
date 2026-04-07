import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from "./App";
import PricingPage from "./pages/PricingPage";
import RecruiterDashboard from "./pages/RecruiterDashboard";
import "./index.css";

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/recruiter/*" element={<RecruiterDashboard />} />
        </Routes>
      </BrowserRouter>
    </React.StrictMode>
  );
}
