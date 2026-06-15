import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import json
from datetime import datetime, timedelta
from prophet import Prophet
import warnings
warnings.filterwarnings('ignore')


class TrendPredictor:
    """趋势预测器 - 基于Prophet模型的市场趋势预测"""
    
    def __init__(self):
        self.model = None
        self.model_type = "prophet"
        self.forecast_periods = 30  # 默认预测30天
        self._training_df = pd.DataFrame()
        
    def prepare_data(self, sentiment_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        准备预测数据
        
        Args:
            sentiment_data: 情绪分析数据
            
        Returns:
            格式化的时间序列数据
        """
        if not sentiment_data:
            return pd.DataFrame()
        
        # 提取时间和情绪得分
        data_points = []
        for news in sentiment_data:
            # 使用发布时间或当前时间
            publish_time = news.get('publish_time', datetime.now().strftime('%Y-%m-%d'))
            sentiment_score = news.get('sentiment_score', 0)
            
            # 转换时间格式
            try:
                if isinstance(publish_time, str):
                    date_obj = datetime.strptime(publish_time[:10], '%Y-%m-%d')
                else:
                    date_obj = publish_time
            except:
                date_obj = datetime.now()
            
            data_points.append({
                'ds': date_obj,
                'y': sentiment_score
            })
        
        df = pd.DataFrame(data_points)
        
        # 按日期聚合，计算每日平均情绪
        if not df.empty:
            df = (
                df.groupby('ds')['y'].mean().reset_index().sort_values('ds')
            )
            df['ds'] = pd.to_datetime(df['ds'])
            df = (
                df.set_index('ds')
                .resample('D')
                .mean()
                .interpolate(method='linear')
                .ffill()
                .bfill()
                .reset_index()
            )
        
        return df
    
    def train_model(self, df: pd.DataFrame) -> bool:
        """
        训练Prophet模型
        
        Args:
            df: 时间序列数据
            
        Returns:
            是否训练成功
        """
        if df.empty or df['ds'].nunique() < 2:
            return False
        
        self._training_df = df.copy()
        
        try:
            # 创建Prophet模型
            self.model = Prophet(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0
            )
            
            # 训练模型
            self.model.fit(df)
            self.model_type = "prophet"
            return True
        except Exception as e:
            print(f"Prophet模型训练失败: {e}")
            baseline_model = self._build_baseline_model(df)
            if baseline_model is not None:
                self.model = baseline_model
                self.model_type = "baseline"
                return True
            print("基线趋势模型构建失败，无法进行趋势预测")
            return False
    
    def predict_trend(self, periods: int = None) -> Dict[str, Any]:
        """
        预测未来趋势
        
        Args:
            periods: 预测天数
            
        Returns:
            预测结果
        """
        if not self.model:
            return {'error': '模型未训练'}
        
        periods = periods or self.forecast_periods
        
        try:
            if self.model_type == "prophet":
                future = self.model.make_future_dataframe(periods=periods)
                forecast = self.model.predict(future)
                prediction_records = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(periods).to_dict('records')
            else:
                forecast, prediction_records = self._forecast_with_baseline(periods)
            
            recent_trend = self._calculate_trend_direction(forecast)
            confidence = self._calculate_confidence(forecast)
            
            return {
                'predictions': prediction_records,
                'trend_direction': recent_trend,
                'confidence': confidence,
                'forecast_periods': periods,
                'model_type': self.model_type
            }
        except Exception as e:
            return {'error': f'预测失败: {e}'}
    
    def _build_baseline_model(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """构建线性回归基线模型，作为Prophet失败时的后备方案"""
        df = df.sort_values('ds').reset_index(drop=True)
        if len(df) < 2:
            return None
        
        try:
            values = df['y'].astype(float).values
            x = np.arange(len(values))
            slope, intercept = np.polyfit(x, values, 1)
            residuals = values - (intercept + slope * x)
            residual_std = float(np.std(residuals)) if len(residuals) > 1 else 0.0
            return {
                'intercept': float(intercept),
                'slope': float(slope),
                'residual_std': residual_std,
                'history': df[['ds', 'y']].copy()
            }
        except Exception:
            return None
    
    def _forecast_with_baseline(self, periods: int) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """使用线性基线模型进行趋势预测"""
        if not isinstance(self.model, dict):
            raise ValueError("基线模型尚未构建")
        
        history_df = self.model.get('history', pd.DataFrame()).copy()
        history_df['ds'] = pd.to_datetime(history_df['ds'])
        history_df = history_df.sort_values('ds').reset_index(drop=True)
        slope = self.model.get('slope', 0.0)
        intercept = self.model.get('intercept', 0.0)
        residual_std = self.model.get('residual_std', 0.0)
        margin = max(residual_std * 1.96, 0.1)
        
        x_hist = np.arange(len(history_df)) if not history_df.empty else np.array([])
        history_yhat = intercept + slope * x_hist if len(x_hist) else np.array([])
        history_forecast = history_df[['ds']].copy() if not history_df.empty else pd.DataFrame({'ds': []})
        if not history_forecast.empty:
            history_forecast['yhat'] = history_yhat
            history_forecast['yhat_lower'] = history_yhat - margin
            history_forecast['yhat_upper'] = history_yhat + margin
        
        future_rows = []
        last_date = history_df['ds'].max() if not history_df.empty else datetime.now()
        for step in range(periods):
            ds_value = last_date + timedelta(days=step + 1)
            x_value = len(history_df) + step
            yhat = intercept + slope * x_value
            lower = yhat - margin
            upper = yhat + margin
            future_rows.append({
                'ds': ds_value,
                'yhat': yhat,
                'yhat_lower': lower,
                'yhat_upper': upper
            })
        
        future_forecast = pd.DataFrame(future_rows)
        combined = pd.concat([history_forecast, future_forecast], ignore_index=True) if not history_forecast.empty else future_forecast
        prediction_records = [
            {
                'ds': row['ds'],
                'yhat': float(row['yhat']),
                'yhat_lower': float(row['yhat_lower']),
                'yhat_upper': float(row['yhat_upper'])
            }
            for row in future_rows
        ]
        return combined, prediction_records
    
    def _calculate_trend_direction(self, forecast: pd.DataFrame) -> str:
        """计算趋势方向"""
        if len(forecast) < 2:
            return 'neutral'
        
        # 比较最后几天的预测值
        recent_values = forecast['yhat'].tail(7).values
        if len(recent_values) < 2:
            return 'neutral'
        
        # 计算斜率
        x = np.arange(len(recent_values))
        slope = np.polyfit(x, recent_values, 1)[0]
        
        if slope > 0.01:
            return 'positive'
        elif slope < -0.01:
            return 'negative'
        else:
            return 'neutral'
    
    def _calculate_confidence(self, forecast: pd.DataFrame) -> float:
        """计算预测置信度"""
        if len(forecast) < 2:
            return 0.0
        
        # 基于预测区间的宽度计算置信度
        recent_forecast = forecast.tail(7)
        avg_uncertainty = (recent_forecast['yhat_upper'] - recent_forecast['yhat_lower']).mean()
        
        # 转换为0-1的置信度分数
        confidence = max(0.0, min(1.0, 1.0 - avg_uncertainty / 2.0))
        return round(confidence, 3)
    
    def analyze_market_sentiment_trend(self, sentiment_data: List[Dict[str, Any]], 
                                     periods: int = 30) -> Dict[str, Any]:
        """
        分析市场情绪趋势
        
        Args:
            sentiment_data: 情绪分析数据
            periods: 预测天数
            
        Returns:
            完整的趋势分析结果
        """
        # 准备数据
        df = self.prepare_data(sentiment_data)
        
        if df.empty:
            return {
                'error': '数据不足，无法进行趋势预测',
                'data_points': 0
            }
        
        # 训练模型
        if not self.train_model(df):
            return {
                'error': '模型训练失败',
                'data_points': len(df)
            }
        
        # 进行预测
        prediction_result = self.predict_trend(periods)
        
        if 'error' in prediction_result:
            return prediction_result
        
        # 生成分析摘要
        analysis_summary = {
            'data_points': len(df),
            'forecast_periods': periods,
            'trend_direction': prediction_result['trend_direction'],
            'confidence': prediction_result['confidence'],
            'predictions': prediction_result['predictions'],
            'historical_data': df.to_dict('records'),
            'model_type': prediction_result.get('model_type', self.model_type)
        }
        
        return analysis_summary
    
    def save_prediction_results(self, results: Dict[str, Any], 
                              file_path: str = "results/logs/trend_prediction.json"):
        """
        保存预测结果
        
        Args:
            results: 预测结果
            file_path: 保存路径
        """
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 添加时间戳
        results['generated_at'] = datetime.now().isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"✅ 趋势预测结果已保存到 {file_path}")
    
    def get_trend_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取趋势摘要
        
        Args:
            results: 预测结果
            
        Returns:
            趋势摘要
        """
        if 'error' in results:
            return {
                'status': 'error',
                'message': results['error']
            }
        
        trend_direction = results.get('trend_direction', 'neutral')
        confidence = results.get('confidence', 0.0)
        
        # 根据趋势方向生成建议
        if trend_direction == 'positive':
            recommendation = "市场情绪呈积极趋势，建议关注相关投资机会"
        elif trend_direction == 'negative':
            recommendation = "市场情绪呈消极趋势，建议谨慎投资"
        else:
            recommendation = "市场情绪相对稳定，建议保持观望"
        
        return {
            'status': 'success',
            'trend_direction': trend_direction,
            'confidence': confidence,
            'recommendation': recommendation,
            'data_points': results.get('data_points', 0),
            'forecast_periods': results.get('forecast_periods', 0),
            'model_type': results.get('model_type', self.model_type)
        }


def predict_market_trend(sentiment_data: List[Dict[str, Any]], periods: int = 30) -> Dict[str, Any]:
    """
    便捷函数：预测市场趋势
    
    Args:
        sentiment_data: 情绪分析数据
        periods: 预测天数
        
    Returns:
        预测结果
    """
    predictor = TrendPredictor()
    return predictor.analyze_market_sentiment_trend(sentiment_data, periods)
