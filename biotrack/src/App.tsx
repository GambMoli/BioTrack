import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';

import { Register,Login,PrincipalPage,SPO2Page,FCPage} from './modules'


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
      </Routes>
    </Router>
      
      
      
    </>
  )
}

export default App
