#!/usr/bin/env python3

from scipy import stats
import matplotlib.pyplot as plt
import pprint
import numpy
import csv
import sys
import os
import re

class CompareResult:
	def __init__(self, metric_a, metric_b):
		self.metric_a = metric_a
		self.metric_b = metric_b

		self.norm_a = metric_a.normalize()
		self.norm_b = metric_b.normalize()

	def time_correlation(self):
		a = self.norm_a
		b = self.norm_b

		corr = numpy.correlate([x[1] for x in a],
		                       [x[1] for x in b], mode="full")
		max_idx = 0
		for i in range(0, len(corr)):
			if corr[i] > corr[max_idx]:
				max_idx = i

		sample_dist = len(a) - max_idx - 1
		time_dist = sample_dist * (a[-1][0] - a[0][0]) / len(a)
		return corr, sample_dist, time_dist

	def diff_histogram(self):
		a = self.norm_a
		b = self.norm_b

		data = list()
		for i in range(0, len(a)):
			data.append(b[i][1] - a[i][1])
		return data, numpy.std(data)

	def scaling_factor(self):
		a = self.norm_a
		b = self.norm_b

		x = list()
		y = list()
		data = list()
		for i in range(0, len(a)):
			x.append(a[i][1])
			y.append(b[i][1] - a[i][1])
			data.append((x[-1], y[-1]))
		return numpy.array(x), numpy.array(y), numpy.polyfit(x, y, deg=1)

	def absolute_error(self):
		a = self.norm_a
		b = self.norm_b

		ra = 0
		for i in range(0, len(a) - 1):
			time_diff = a[i+1][0] - a[i][0]
			ra += a[i][1] * time_diff

		rb = 0
		for i in range(0, len(a) - 1):
			time_diff = b[i+1][0] - b[i][0]
			rb += b[i][1] * time_diff

		return rb - ra

class Metric:
	def __init__(self, name, unit, data, data_raw_file):
		self.name = name
		self.unit = unit
		self.data = data
		self.data_raw_file = data_raw_file

		self._cache_result = None

	def average(self):
		if self._cache_result is None:
			s = sum(row[1] for row in self.data)
			self._cache_result = s / len(self.data)
		return self._cache_result

	def integrate(self):
		r = 0
		for i in range(0, len(self.data) - 1):
			time_diff = self.data[i+1][0] - self.data[i][0]
			r += self.data[i][1] * time_diff

		return r

	def exec_time(self):
		if len(self.data) > 0:
			return self.data[-1][0]
		else:
			return 0

	def normalize(self):
		data = list()

		avr = 0
		for pt in self.data:
			avr += pt[1]
		avr = avr / len(self.data)

		for v in self.data:
			pt = (v[0], v[1] - avr)
			data.append(pt)

		return data

	def compare(self, metric):
		return CompareResult(self, metric)


def parse_metric_file(metric_file, prefix_name):
	output = dict()
	values = dict()
	with open(metric_file, 'rt') as f:

		reader = csv.DictReader(f)
		try:
			# Collect stats about each metrics
			for row in reader:
				if row is None or len(row) == 0:
					continue

				# Verify that all the fields are present or abort...
				allValuesOK = True
				for field in values:
					if row[field] is None:
						allValuesOK = False
						break
				if not allValuesOK:
					break

				for field in row:
					if field not in values:
						values[field] = list()
					values[field].append(float(row[field]))
		except csv.Error as e:
			sys.stderr.write('file %s, line %d: %s\n' % (filepath, reader.line_num, e))
			return [], "none"

	# Find the time values and store them aside after converting them to seconds
	time_unit_re = re.compile(r'^time \((.+)\)$')
	time = list()
	for field in values:
		m = time_unit_re.match(field)
		if m is not None:
			unit = m.groups()[0]
			factor = 1
			if unit == "s":
				factor = 1
			elif unit == "ms":
				factor = 1e-3
			elif unit == "us" or unit == "µs":
				factor = 1e-6
			elif unit == "ns":
				factor = 1e-9
			else:
				print("unknown time unit '{}'".format(unit))
			for v in values[field]:
				time.append(v * factor)

	# Create the metrics
	metric_name_re = re.compile(r'^(.+) \((.+)\)$')
	for field in values:
		unit = None
		m = metric_name_re.match(field)
		if m is not None:
			metric_name, unit = m.groups()
		else:
			metric_name = field

		if metric_name.lower() == "time":
			continue

		metric_name = "{}{}".format(prefix_name, metric_name)
		metric = Metric(metric_name, unit, [], metric_file)
		for v in range(0, len(values[field])):
			metric.data.append((time[v], values[field][v]))
		output[metric_name] = metric

	return output

def merge_metric_files(files):
	output_metrics = dict()

	fields = dict()
	for f in files:
		fields.update(parse_metric_file(f, ""))

	index = dict()
	for field in fields:
		index[field] = 1

	#print('time (ms)', end="")
	for field in fields:
		output_metrics[field] = list()
		#print(',{} ({})'.format(field, fields[field].unit), end="")
	#print("")

	exit = False
	while not exit:
		for field in fields:
			if index[field] >= len(fields[field].data):
				exit = True
				break
		if exit:
			break

		time = sys.maxsize
		min_fields = []
		for field in fields:
			if fields[field].data[index[field]][0] < time:
				time = fields[field].data[index[field]][0]
				min_fields = []
			if fields[field].data[index[field]][0] == time:
				min_fields.append(field)

		if time == sys.maxsize:
			break

		#print('{:.3f}'.format(time), end="")
		for field in fields:
			next_time, next_val = fields[field].data[index[field]]
			assert(next_time >= time)

			# Interpolate to decrease difference between the outputs
			last_time, last_val = fields[field].data[index[field] - 1]
			#print("time = {}, last_time = {}".format(time, last_time))
			#assert((time - last_time) >= 0)
			time_ratio = (time - last_time) / (next_time - last_time)
			val = last_val + (next_val - last_val) * time_ratio
			output_metrics[field].append((time, val))
			#print(',{:.2f}'.format(val), end="")

		#print("")

		for field in min_fields:
			index[field] += 1

	metrics = dict()
	for field in fields:
		metrics[field] = Metric(field, fields[field].unit, output_metrics[field],
		                        fields[field].data_raw_file)
	return metrics

def plot(axis, data, name, style = None):
	x = [p[0] for p in data]
	y = [p[1] for p in data]

	if style is None:
		axis.plot(x, y, label=name)
	else:
		axis.plot(x, y, style, label=name)

if __name__ == "__main__":
	import argparse

	# parse the options
	parser = argparse.ArgumentParser()
	parser.add_argument("-c", dest="check_run", help="RAPL/power meter comparaison")
	parser.add_argument("-m", dest="merge", help="Merge the metrics")
	args = parser.parse_args()

	if args.check_run is not None:
		metrics = merge_metric_files([args.check_run + ".metrics_envdump",
							args.check_run + ".metrics_pwr_yoko"])

		results = metrics['system power'].compare(metrics['rapl0.package-0'])

		fig = plt.figure()
		ax0 = plt.subplot2grid((5, 2), (0, 0))
		ax1 = plt.subplot2grid((5, 2), (0, 1))
		ax2 = plt.subplot2grid((5, 2), (1, 0))
		ax3 = plt.subplot2grid((5, 2), (1, 1))
		ax4 = plt.subplot2grid((5, 2), (2, 0), colspan=2)
		ax5 = plt.subplot2grid((5, 2), (3, 0), colspan=2, rowspan=2)

		system_name = "{} ({:.1f} J)".format(metrics['system power'].name, metrics['system power'].integrate())
		rapl_name = "{} ({:.1f} J)".format(metrics['rapl0.package-0'].name, metrics['rapl0.package-0'].integrate())

		plot(ax0, metrics['system power'].data, system_name)
		plot(ax0, metrics['rapl0.package-0'].data, rapl_name)
		ax0.set_title('Raw power consumptions')
		ax0.set_xlabel('Time (s)')
		ax0.set_ylabel('Power (W)')
		ax0.legend(loc='upper left', shadow=True)

		plot(ax1, results.norm_a, results.metric_a.name)
		plot(ax1, results.norm_b, results.metric_b.name)
		ax1.set_title('Normalized power consumptions (diff = {:.2f} Joules)'.format(results.absolute_error()))
		ax1.set_xlabel('Time (s)')
		ax1.set_ylabel('Normalized power (W)')
		ax1.legend(loc='upper left', shadow=True)

		corr, sample_dist, time_dist = results.time_correlation()
		ax2.plot(range(len(corr)), corr)
		ax2.set_title('Time correlation (diff = {} s)'.format(time_dist))
		ax2.set_xlabel('Bin')
		ax2.set_ylabel('Correlation')
		ax2.axvline((len(corr) / 2) - 0.5, label="Expected peak", color="red")
		ax2.legend(loc='upper left', shadow=True)

		data, std = results.diff_histogram()
		ax3.hist(data, 50, normed=1, facecolor='green', alpha=0.5)
		ax3.set_title('Difference Histogram (std = {:.3f})'.format(std))
		ax3.set_xlabel('Difference (W)')
		ax3.set_ylabel('Probabily occurence')
		ax3.legend(loc='upper left', shadow=True)

		x, y, regress = results.scaling_factor()
		ax4.plot(x, y, 'o')
		ax4.set_title('Scaling factor scatter plot')
		ax4.set_ylabel('package - system power (W)')
		ax4.set_xlabel('Normalized system power (W)')
		ax4.plot(x, regress[0] * x + regress[1], color='red',
		   label="regression ({:.3f} * x + {:.3f})".format(regress[0], regress[1]))
		ax4.legend(loc='lower left', shadow=True)

		for i in range(len(results.norm_b)):
			results.norm_b[i] = (results.norm_b[i][0], results.norm_b[i][1] + (results.norm_b[i][1] - results.norm_a[i][1]) * regress[0] + regress[1])
		plot(ax5, results.norm_a, results.metric_a.name)
		plot(ax5, results.norm_b, results.metric_b.name)
		ax5.set_title('Corrected normalized power consumptions (diff = {:.2f} Joules)'.format(results.absolute_error()))
		ax5.set_xlabel('Time (s)')
		ax5.set_ylabel('Normalized power (W)')
		ax5.legend(loc='upper left', shadow=True)

		figManager = plt.get_current_fig_manager()
		figManager.window.showMaximized()
		plt.show()

	elif args.merge is not None:
		metrics = merge_metric_files([args.merge + ".metrics_envdump",
							args.merge + ".metrics_pwr_yoko"])

		print("time (ms), rapl0.package-0 (W), system power (W)")
		for i in range(0, len(metrics['rapl0.package-0'].data)):
			print("{:.2f}, {:.2f}, {:.2f}".format(metrics['rapl0.package-0'].data[i][0],
								metrics['rapl0.package-0'].data[i][1],
								metrics['system power'].data[i][1]))
