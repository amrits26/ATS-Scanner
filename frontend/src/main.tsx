import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from "./App";
import PricingPage from "./pages/PricingPage";
import RecruiterDashboard from "./pages/RecruiterDashboard";
import RecruiterLanding from "./pages/RecruiterLanding";
import { TailorSuccessPage } from "./pages/TailorSuccessPage";
import UserDashboard from "./pages/UserDashboard";
import "./index.css";

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/tailor-rewrite/:sessionId" element={<TailorSuccessPage />} />
          <Route path="/dashboard" element={<UserDashboard />} />
          <Route path="/recruiter/signup" element={<RecruiterLanding />} />
          <Route path="/recruiter/*" element={<RecruiterDashboard />} />
        </Routes>
      </BrowserRouter>
    </React.StrictMode>
  );
}
