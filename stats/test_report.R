#!/usr/bin/Rscript

# Copyright (c) 2015, Intel Corporation
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of Intel Corporation nor the names of its contributors
#       may be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

args <- commandArgs(trailingOnly = TRUE)
if(length(args) != 2) {
    cat("Usage:\n\t./test_report.R input.csv output.png\n\n")
    q(save="no")
}

data <- read.csv(args[1])

d <- density(data[[1]])

png(args[2], width = 1900, height = 200)

layout(matrix(c(1,2), 1), c(3.5,1), c(1,3))
par(mar=c(4.3, 4.3, 2.0, 0.1))

plot(data[[1]], ylab="FPS", xlab="FPS sample", main="Time series of the FPS",
     cex.lab=1.5, cex.axis=1.5, cex.main=1.5, cex.sub=1.5)
lines(data[[1]], type="l")
abline(h=mean(data[[1]]),col=4)
abline(h=median(data[[1]]),col=2)

plot(d, xlab="FPS", main="Density function of the FPS", cex.lab=1.5,
     cex.axis=1.5, cex.main=1.5, cex.sub=1.5)
abline(v=mean(data[[1]]),col=4)
abline(v=median(data[[1]]),col=2)
