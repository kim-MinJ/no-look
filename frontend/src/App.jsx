import FaceDetector from './components/FaceDetector';
import Dashboard from './pages/Dashboard';
import './styles/dashboard.css';

function App() {
  return (
    <div className="App">
      <h1>Auto-Chat Bot (Frontend MediaPipe)</h1>
      <FaceDetector />
      <Dashboard />
    </div>
  );
}

export default App;
