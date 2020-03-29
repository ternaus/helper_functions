from collections import defaultdict
from typing import Dict, List, Union, Any

import numpy as np
import pandas as pd
from addict import Dict as Addict
from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import MinMaxScaler as MX


class CyclicEncoder:
    """
    Class encodes feature x to (cos(2 pi x / amplitude), sin(2 * pi x / amplitude)
    """

    params: Dict[str, float] = {}

    def __init__(self, amplitude):
        self.params["amplitude"] = amplitude

    def fit(self, x):
        pass

    def fit_transform(self, x: Union[np.array, list]) -> np.array:
        return self.transform(x)

    def get_params(self) -> dict:
        return self.params

    def set_params(self, params: dict) -> None:
        self.params = params

    def inverse_transform(self, x: np.array) -> np.array:
        sin_component = x[:, 1]
        cos_component = x[:, 0]
        angle = np.arctan(sin_component / cos_component) + np.pi / 2 * (1 - np.sign(cos_component))
        return angle * self.params["amplitude"] / (2 * np.pi)

    def transform(self, x: Union[list, np.array]) -> np.array:
        amplitude = self.params["amplitude"]
        argument = 2 * np.pi * x / amplitude
        cos_component = np.cos(argument)
        sin_component = np.sin(argument)

        result = np.vstack([cos_component, sin_component]).T

        return result


class MinMaxScaler:
    """
    Extension of MinMaxScaler to work with 1d arrays
    """

    def __init__(self, feature_range):
        self.encoder = MX(feature_range=feature_range)
        self.feature_range = feature_range

    def fit(self, x: Union[list, np.array]) -> None:
        if not isinstance(x, type(np.array)):
            x = np.array(x)

        x = x.reshape(-1, 1)

        self.encoder.fit(x)
        self.data_min_ = self.encoder.data_min_
        self.data_max_ = self.encoder.data_max_
        self.data_range_ = self.encoder.data_range_
        self.scale_ = self.encoder.scale_

    def transform(self, x: Union[np.array, list]) -> np.array:
        if not isinstance(x, type(np.array)):
            x = np.array(x)

        x = x.reshape(-1, 1)

        return self.encoder.transform(x).T

    def fit_transform(self, x: Union[np.array, list]) -> np.array:
        self.fit(x)
        return self.transform(x)

    def inverse_transform(self, x: Union[np.array, list]) -> np.array:
        if not isinstance(x, type(np.array)):
            x = np.array(x)

        x = x.reshape(-1, 1)
        return self.encoder.inverse_transform(x).T[0]


class LabelEncoderUnseen(LabelEncoder):
    """Extension of sklearn.preprocessing.LabelEncoder
    that can work with unseen labels.
    All unseen labels are mapped to 'uknown_class'
    """

    set_classes: set

    def __init__(self, unknown_class="unknown"):
        super().__init__()
        self.unknown_class = unknown_class

    def fit(self, x: Union[np.array, list]) -> None:
        super().fit([self.unknown_class] + list(x))
        self.set_classes = set(self.classes_)

    def transform(self, x: Union[np.array, list]) -> np.array:
        if isinstance(x, pd.core.series.Series):
            x = x.values

        for i in range(len(x)):
            if x[i] not in self.set_classes:
                x[i] = self.unknown_class

        return super().transform(x)

    def fit_transform(self, x: Union[np.array, list]) -> np.array:
        self.fit(x)
        return self.transform(x)


class Column:
    def __init__(self, input: Any, category_type: str):
        if len(input) == 2:
            self.name = input[0]
            self.amplitude = input[1]

        else:
            self.name = input

        self.category_type = category_type

    def __repr__(self):
        return f"name: {self.name}\n" f"category_type: {self.category_type}\n"


class GeneralEncoder:
    """Generate encoders for tabular data transforms.

    numerical: (x - min(x)) / (max(x) - min(x)) i.e. MinMaxScaler
    categorical: OneHotEncoding(x) i.e. OneHotEncoder

    cyclical: x => (cos(2 * pi * x / amplitude), sin(2 * pi * x / amplitude))

    args:
        df: pandas dataframe to transform.
        columns_map: dictionary of the type:
            {
                "numerical": [column1, column2, ...],
                "categorical": [column3, column4, ...],
                "cyclical": [(column5, cyclic_amplitude5), (column6, cyclic_amplitude6), ...]
                "joined_encoders": {column1: [column1a, column2a, ...]} # optional
            }

    return:
        dictionary:
            {
                "numerical": [column1, column2, ...],
                "categorical": [column3, column4, ...],
                "cyclical": [(cos(column_5) sin(column_5), (cos(column_6) sin(column_6), ...]
            }

    """

    encoders: Addict
    column2type: Dict[str, str] = {}
    columns: List = []
    columns_map: Dict[str, list]

    def __init__(self, columns_map):
        self.columns_map = columns_map

        self.type2encoder = {
            "numerical": (MinMaxScaler, {"feature_range": (-1, 1)}),
            "categorical": (LabelEncoderUnseen, {}),
            "cyclical": (CyclicEncoder, {}),
        }

        if "joined_encoders" in self.columns_map:
            self.joined_encoders = self.columns_map["joined_encoders"]
            del columns_map["joined_encoders"]
        else:
            self.joined_encoders = {}

        if set(self.type2encoder.keys()).intersection(columns_map.keys()) != set(columns_map.keys()):
            raise ValueError(f"Wrong column names in columns_map {columns_map}.")

        self.category_types = set(self.columns_map.keys())

        self.column2type = self.get_columns2type()

        self.column_classes = Addict()

        for category_type in self.category_types:
            for column in columns_map[category_type]:
                self.column_classes[column] = Column(column, category_type=category_type)

        for column_name, column_names in self.joined_encoders.items():
            category_type = self.column2type[column_name]
            for subcolumn_name in column_names:
                self.column_classes[subcolumn_name] = Column(subcolumn_name, category_type=category_type)

        self.numerical_columns = self._get_columns("numerical")
        self.categorical_columns = self._get_columns("categorical")
        self.cyclical_columns = self._get_columns("cyclical")

    def get_columns2type(self):
        result = {}

        for category_type in self.category_types:
            for column in self.columns_map[category_type]:
                if category_type == "cyclical":
                    result[column[0]] = category_type
                else:
                    result[column] = category_type

        for column_name, values in self.joined_encoders.items():
            for subcolumn_name in values:
                result[subcolumn_name] = result[column_name]

        return result

    def _get_columns(self, category_type):
        if category_type not in self.category_types:
            return []

        return [x.name for x in self.column_classes.values() if x.category_type == category_type]

    def fit(self, df: pd.DataFrame) -> None:
        self.columns = list(df.columns)
        self.encoders = Addict()

        for column_name, subcolumn_names in self.joined_encoders.items():
            if column_name in self.encoders:
                raise ValueError(
                    f"We should not have same column in two joined columns! " f"But we got it for {column_name}"
                )

            category_type = self.column2type[column_name]
            encoder_class, parameters = self.type2encoder[category_type]

            encoder = encoder_class(**parameters)

            x = [df[column_name].values]

            if category_type == "categorical":
                for subcolumn_name in subcolumn_names:
                    x += [df[subcolumn_name].values]

                x = np.concatenate(x)

            encoder.fit(x)

            self.encoders[column_name] = encoder

            for subcolumn_name in subcolumn_names:
                if subcolumn_name in self.encoders:
                    raise ValueError(
                        f"We should not have same subcolumn in two joined columns! "
                        f"But we got it for {subcolumn_name}"
                    )

                self.encoders[subcolumn_name] = encoder

        for category_type, column_names in self.columns_map.items():
            encoder_class, parameters = self.type2encoder[category_type]

            for column_name in column_names:
                if column_name in self.encoders:
                    continue

                if category_type == "cyclical":
                    parameters["amplitude"] = column_name[1]

                    column = column_name[0]
                else:
                    column = column_name

                encoder = encoder_class(**parameters)

                x = df[column].values

                encoder.fit(x)
                self.encoders[column] = encoder

    def fit_transform(self, df: pd.DataFrame) -> Dict[str, list]:
        self.fit(df)
        return self.transform(df)

    def transform(self, df: pd.DataFrame) -> Dict[str, list]:
        if self.encoders == {}:
            raise ValueError(f"Perform fit before calling transform.")

        result: defaultdict = defaultdict(list)

        for category_type, columns_list in (
            ["numerical", self.numerical_columns],
            ["cyclical", self.cyclical_columns],
            ["categorical", self.categorical_columns],
        ):
            for column_name in columns_list:
                encoder = self.encoders[column_name]

                x = df[column_name].values
                encoded = encoder.transform(x)

                result[category_type] += [encoded]

        return result

    def get_params(self):
        return self.encoders, self.column2type

    def inverse_transform(self, feature_dict):
        result = {}

        for category_type, columns_list in (
            ["numerical", self.numerical_columns],
            ["cyclical", self.cyclical_columns],
            ["categorical", self.categorical_columns],
        ):

            for column_id, column_name in enumerate(columns_list):
                if column_name not in self.encoders:
                    raise KeyError(f"We do not have {column_name} in self encoders {self.encoders}.")

                encoder = self.encoders[column_name]
                x = feature_dict[category_type][column_id]

                result[column_name] = encoder.inverse_transform(x)

        return pd.DataFrame(result)[self.columns]
