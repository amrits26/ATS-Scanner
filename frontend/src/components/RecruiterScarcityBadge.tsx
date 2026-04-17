import React, { useEffect, useState } from 'react';

interface ScarcityData {
    count: number;
    message: string;
    message_variant: string;
    expires_soon_count: number;
}

interface RecruiterScarcityBadgeProps {
    skills?: string;
    locationState?: string;
    minScore?: number;
    recruiterEmail: string;
    onCountChange?: (count: number) => void;
}

export function RecruiterScarcityBadge({
    skills,
    locationState,
    minScore = 85,
    recruiterEmail,
    onCountChange,
}: RecruiterScarcityBadgeProps) {
    const [scarcityData, setScarcityData] = useState<ScarcityData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch scarcity count when filters change
    useEffect(() => {
        const fetchScarcityCount = async () => {
            if (!recruiterEmail) return;

            setLoading(true);
            setError(null);

            try {
                const params = new URLSearchParams();
                if (skills) params.append('skills', skills);
                if (locationState) params.append('location_state', locationState);
                params.append('min_score', String(minScore));
                params.append('recruiter_email', recruiterEmail);

                const response = await fetch(
                    `/api/recruiter/candidates/count?${params.toString()}`,
                    {
                        headers: {
                            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
                        },
                    }
                );

                if (response.ok) {
                    const data = await response.json();
                    setScarcityData(data);
                    onCountChange?.(data.count);
                } else {
                    setError('Failed to fetch candidate count');
                }
            } catch (err) {
                console.error('Failed to fetch scarcity count:', err);
                setError('Error loading candidate count');
            } finally {
                setLoading(false);
            }
        };

        // Debounce the fetch to avoid too many requests
        const timer = setTimeout(fetchScarcityCount, 300);
        return () => clearTimeout(timer);
    }, [skills, locationState, minScore, recruiterEmail, onCountChange]);

    if (loading) {
        return (
            <div className="scarcity-badge scarcity-loading">
                <span className="spinner" />
                <p>Loading candidates...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="scarcity-badge scarcity-error">
                <p className="scarcity-message">{error}</p>
            </div>
        );
    }

    if (!scarcityData) {
        return null;
    }

    return (
        <div className={`scarcity-badge scarcity-${scarcityData.message_variant}`}>
            <p className="scarcity-message">{scarcityData.message}</p>
            <span className="candidate-count">
                {scarcityData.count} matching candidate{scarcityData.count !== 1 ? 's' : ''}
            </span>
            {scarcityData.expires_soon_count > 0 && (
                <span className="expires-soon">
                    ({scarcityData.expires_soon_count} expiring within 24h)
                </span>
            )}
        </div>
    );
}
