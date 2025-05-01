import { API_ENDPOINTS, createFetchOptions, handleApiResponse } from '../api/config';

const fetchDashboardData = useCallback(async () => {
  if (!isAuthenticated) {
    setIsLoading(false);
    return;
  }
  setIsLoading(true);
  setError(null);
  
  try {
    const fetchOptions = await createFetchOptions(getToken);
    console.log('Fetching dashboard data with options:', {
      ...fetchOptions,
      headers: Object.fromEntries(Object.entries(fetchOptions.headers))
    });

    // Fetch all data concurrently with proper error handling
    const [statsData, distributionData, recentDocsData] = await Promise.all([
      fetch(API_ENDPOINTS.dashboard.stats, fetchOptions)
        .then(handleApiResponse)
        .catch(err => {
          console.error('Stats fetch failed:', err);
          throw err;
        }),
      fetch(API_ENDPOINTS.dashboard.scoreDistribution, fetchOptions)
        .then(handleApiResponse)
        .catch(err => {
          console.error('Distribution fetch failed:', err);
          throw err;
        }),
      fetch(API_ENDPOINTS.documents.recent(), fetchOptions)
        .then(handleApiResponse)
        .catch(err => {
          console.error('Recent documents fetch failed:', err);
          throw err;
        })
    ]);

    // Log successful responses
    console.log('Dashboard data fetched successfully:', {
      stats: statsData,
      distribution: distributionData,
      recentDocs: recentDocsData
    });

    // Update state with fetched data
    setKeyStats(statsData);
    setChartData(distributionData);
    setRecentAssessments(recentDocsData);

  } catch (err) {
    console.error("Dashboard: Error fetching data:", {
      message: err.message,
      stack: err.stack,
      token: 'Bearer token present: ' + Boolean(await getToken())
    });
    setError(err.message || "Failed to load dashboard data.");
    // Clear potentially partial data on error
    setKeyStats(null);
    setChartData([]);
    setRecentAssessments([]);
  } finally {
    setIsLoading(false);
  }
}, [isAuthenticated, getToken]); 