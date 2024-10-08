import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';

import { Register,Login,PrincipalPage,SPO2Page,FCPage,HistorialOxigeno,HistorialFrecuencia} from './modules'


function App() {
  

  return (
    <>
    <Router>
      <Routes>
        {/* Define la ruta para la página de inicio */}
        <Route path="/Login" element={<Login />} />
        
       
        <Route path="/register" element={<Register />} />

        <Route path="/Home" element={<PrincipalPage />} />
        <Route path="/MedidorOxigeno" element={<SPO2Page />} />
        <Route path="/MedidorFrecuencia" element={<FCPage />} />
        <Route path="/HistorialO2" element={<HistorialOxigeno />} />
        <Route path="/HistorialFC" element={<HistorialFrecuencia />} />
      </Routes>
    </Router>
      
      
      
    </>
  )
}

export default App
