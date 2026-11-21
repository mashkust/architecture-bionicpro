import React, { useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const apiFetch = async (path: string, init?: RequestInit): Promise<Response> => {
    if (!keycloak?.token) {
      throw new Error('Not authenticated');
    }

    const request = (token: string) => {
      const headers = new Headers(init?.headers);
      headers.set('Authorization', `Bearer ${token}`);
      return fetch(`${process.env.REACT_APP_API_URL}${path}`, {
        ...init,
        headers
      });
    };

    let response = await request(keycloak.token);

    if (response.status === 401) {
      try {
        await keycloak.updateToken(30);
      } catch {
        keycloak.login();
        throw new Error('Session expired, please log in again');
      }
      if (!keycloak.token) {
        throw new Error('Not authenticated');
      }
      response = await request(keycloak.token);
    }

    return response;
  };

  const errorDetail = async (response: Response): Promise<string> => {
    const text = await response.text();
    try {
      const body = JSON.parse(text);
      if (body.detail) {
        return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // not JSON
    }
    return text || response.statusText;
  };

  const downloadReport = async () => {
    try {
      setLoading(true);
      setError(null);
      setStatus(null);

      const response = await apiFetch('/reports');

      if (!response.ok) {
        setError(`Request failed: HTTP ${response.status} ${await errorDetail(response)}`);
        return;
      }
      setStatus('Report is ready.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async () => {
    try {
      setLoading(true);
      setError(null);
      setStatus(null);

      const response = await apiFetch('/reports/generate', { method: 'POST' });

      if (!response.ok) {
        setError(`Generation failed: HTTP ${response.status} ${await errorDetail(response)}`);
        return;
      }

      const body = await response.json();
      if (body.status === 'already_generated') {
        setStatus(
          `Report for ${body.report_date} is already generated (DAG run ${body.dag_run_id}). Click Download Report.`
        );
      } else {
        setStatus(
          `Generation started for ${body.report_date} (DAG run ${body.dag_run_id}). Wait ~30 seconds, then click Download Report.`
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  if (!initialized) {
    return <div>Loading...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md">
        <h1 className="text-2xl font-bold mb-6">Usage Reports</h1>

        <div className="flex justify-center gap-4">
          <button
            onClick={generateReport}
            disabled={loading}
            className={`px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 ${
              loading ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            {loading ? 'Generating...' : 'Generate Report'}
          </button>

          <button
            onClick={downloadReport}
            disabled={loading}
            className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
              loading ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            {loading ? 'Generating...' : 'Download Report'}
          </button>

          <button
            onClick={() => keycloak.logout({ redirectUri: window.location.origin })}
            className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600"
          >
            Logout
          </button>
        </div>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">
            {error}
          </div>
        )}

        {status && (
          <div className="mt-4 p-4 bg-green-100 text-green-700 rounded">
            {status}
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;