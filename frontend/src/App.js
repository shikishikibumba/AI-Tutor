import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { ModuleProvider } from "@/context/ModuleContext";
import Layout from "@/components/Layout";
import RequireModule from "@/components/RequireModule";
import Dashboard from "@/pages/Dashboard";
import Tutor from "@/pages/Tutor";
import QuestionBank from "@/pages/QuestionBank";
import Practice from "@/pages/Practice";
import MockExam from "@/pages/MockExam";
import Mistakes from "@/pages/Mistakes";
import StudyPlan from "@/pages/StudyPlan";
import Admin from "@/pages/Admin";

const guard = (el) => <RequireModule>{el}</RequireModule>;

function App() {
  return (
    <ModuleProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/admin" element={<Admin />} />
          <Route element={<Layout />}>
            <Route path="/" element={guard(<Dashboard />)} />
            <Route path="/tutor" element={guard(<Tutor />)} />
            <Route path="/bank" element={guard(<QuestionBank />)} />
            <Route path="/practice" element={guard(<Practice />)} />
            <Route path="/exam" element={guard(<MockExam />)} />
            <Route path="/mistakes" element={guard(<Mistakes />)} />
            <Route path="/plan" element={guard(<StudyPlan />)} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster theme="dark" position="top-right" />
    </ModuleProvider>
  );
}

export default App;
